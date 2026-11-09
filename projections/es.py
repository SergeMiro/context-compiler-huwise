"""Cards -> Elasticsearch. One index for all portals, routed and filtered by portal: a tenant never sees another."""
import time

from django.conf import settings
from elasticsearch import Elasticsearch, NotFoundError, helpers

from catalog.models import Dataset
from ctx.compile import current

_es = None
MAPPING = {
    "settings": {
        "number_of_shards": 1, "number_of_replicas": 0,
        "analysis": {
            "filter": {
                "fr_elision": {"type": "elision", "articles_case": True,
                               "articles": ["l", "m", "t", "qu", "n", "s", "j", "d", "c", "jusqu", "quoiqu", "lorsqu", "puisqu"]},
                "fr_stop": {"type": "stop", "stopwords": "_french_"},
                "fr_stem": {"type": "stemmer", "language": "light_french"},
            },
            # asciifolding: "college" finds "collège", "eleves" finds "élèves"
            "analyzer": {"fr": {"tokenizer": "standard",
                                "filter": ["fr_elision", "lowercase", "asciifolding", "fr_stop", "fr_stem"]}},
        },
    },
    "mappings": {
        "dynamic": "strict",
        "properties": {
            "portal": {"type": "keyword"},
            "dataset_id": {"type": "keyword", "fields": {"text": {"type": "text", "analyzer": "fr"}}},
            "title": {"type": "text", "analyzer": "fr"},
            "keywords": {"type": "text", "analyzer": "fr"},
            "description": {"type": "text", "analyzer": "fr"},
            "field_text": {"type": "text", "analyzer": "fr"},
            "themes": {"type": "keyword"},
            "modified": {"type": "date"},
            "records_count": {"type": "long"},
            "usage_count": {"type": "long"},
            "version": {"type": "integer"},
            "short": {"type": "text", "index": False},
        },
    },
}
COMPILED_FIELDS = ["title^3", "keywords^2", "dataset_id.text^2", "description", "field_text"]
NAKED_FIELDS = ["title^3", "description"]  # what a generic catalog search sees
# usage signal added to the BM25 score: sqrt(3389 agent calls) * 0.05 = +2.9 for the most used dataset.
# Tuned on 11 probe questions (NOTES.md, T8b): top-5 9/11 -> 11/11. Kept out of the naked baseline.
USAGE_FACTOR = 0.05


def client():
    global _es
    if _es is None:
        _es = Elasticsearch(settings.ES_URL, request_timeout=10)
    return _es


def ensure_index():
    es, alias = client(), settings.ES_INDEX
    if not es.indices.exists_alias(name=alias):
        name = f"{alias}_v{int(time.time())}"
        es.indices.create(index=name, **MAPPING)
        es.indices.put_alias(index=name, name=alias)


def doc(ds, card):
    synonyms = [s.strip() for e in ds.edits.all() if e.status == "kept" and e.kind == "synonyms"
                for s in e.after.split(",")]
    return {
        # synonyms live in the title field: a field few documents have gets a near-zero IDF in BM25
        "portal": ds.portal.domain, "dataset_id": ds.dataset_id, "title": [ds.title, *synonyms],
        "keywords": " ".join(ds.keywords), "description": ds.description,
        "field_text": " ".join(f"{f.name} {f.label} {f.description}" for f in ds.fields.all()),
        "themes": ds.themes, "modified": ds.modified, "records_count": ds.records_count,
        "usage_count": ds.usage_count, "version": card.version, "short": card.short,
    }


def _actions(datasets, index):
    for ds in datasets:
        card = current(ds)
        if card:
            yield {"_index": index, "_id": f"{ds.portal.domain}/{ds.dataset_id}", "_routing": ds.portal.domain,
                   "_source": doc(ds, card)}


def _datasets(portal):
    return Dataset.objects.filter(portal=portal).select_related("portal").prefetch_related("fields", "edits", "cards")


def project_es(portal):
    """Replace this portal's documents. Other portals are untouched."""
    ensure_index()
    es, alias = client(), settings.ES_INDEX
    es.delete_by_query(index=alias, routing=portal.domain, query={"term": {"portal": portal.domain}},
                       refresh=True, conflicts="proceed")
    ok, _ = helpers.bulk(es, _actions(_datasets(portal), alias))
    es.indices.refresh(index=alias)
    return ok


def upsert_es(ds):
    ensure_index()
    for a in _actions([ds], settings.ES_INDEX):
        client().index(index=a["_index"], id=a["_id"], routing=a["_routing"], document=a["_source"], refresh=True)


def rebuild_index(portals):
    """Mapping changed: build <alias>_vN for all portals, switch the alias atomically, drop the old index."""
    es, alias = client(), settings.ES_INDEX
    new = f"{alias}_v{int(time.time() * 1000)}"
    es.indices.create(index=new, **MAPPING)
    ok = 0
    for p in portals:
        ok += helpers.bulk(es, _actions(_datasets(p), new))[0]
    es.indices.refresh(index=new)
    old = list(es.indices.get_alias(name=alias)) if es.indices.exists_alias(name=alias) else []
    es.indices.update_aliases(actions=[{"remove": {"index": i, "alias": alias}} for i in old]
                              + [{"add": {"index": new, "alias": alias}}])
    for i in old:
        es.indices.delete(index=i)
    return ok, new


def _query(portal_domain, q, naked):
    text = {"bool": {"must": [{"multi_match": {"query": q, "fields": NAKED_FIELDS if naked else COMPILED_FIELDS,
                                                "type": "cross_fields", "operator": "or"}}],
                     "filter": [{"term": {"portal": portal_domain}}]}}
    if naked:
        return text
    return {"function_score": {"query": text, "boost_mode": "sum", "field_value_factor": {
        "field": "usage_count", "modifier": "sqrt", "factor": USAGE_FACTOR, "missing": 0}}}


def search(portal_domain, q, k=5, naked=False):
    try:
        r = client().search(
            index=settings.ES_INDEX, routing=portal_domain, size=k,
            query=_query(portal_domain, q, naked),
            source=["dataset_id", "title", "short", "description"])
    except NotFoundError:
        return []
    return [{"dataset_id": h["_source"]["dataset_id"], "title": h["_source"]["title"][0], "score": round(h["_score"], 2),
             "short": h["_source"]["short"], "description": h["_source"]["description"]} for h in r["hits"]["hits"]]


def drop_index():
    """Tests only: remove the alias and its indices."""
    es, alias = client(), settings.ES_INDEX
    if es.indices.exists_alias(name=alias):
        for i in list(es.indices.get_alias(name=alias)):
            es.indices.delete(index=i)
