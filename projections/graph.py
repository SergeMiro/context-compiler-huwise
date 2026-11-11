"""Datasets -> Neo4j. Linear-size model: (:Dataset)-[:HAS_KEY]->(:Key)<-[:HAS_KEY]-(:Dataset) instead of an edge per pair
(on `uai` that is 79 edges instead of 3 081). Lineage: (:Dataset)-[:DERIVED_FROM]->(:Dataset)."""
from django.conf import settings
from neo4j import GraphDatabase

from catalog.models import Field, Transformation
from sources.keys import key_of

_driver = None
BATCH = 500
SCHEMA = [
    "CREATE CONSTRAINT dataset_id IF NOT EXISTS FOR (d:Dataset) REQUIRE (d.portal, d.dataset_id) IS UNIQUE",
    "CREATE CONSTRAINT key_name IF NOT EXISTS FOR (k:Key) REQUIRE k.name IS UNIQUE",
]


def driver():
    global _driver
    if _driver is None:
        # lineage queries name DERIVED_FROM before any such edge exists: not a typo, silence that warning
        _driver = GraphDatabase.driver(settings.NEO4J_URL, auth=settings.NEO4J_AUTH,
                                       notifications_disabled_classifications=["UNRECOGNIZED"])
    return _driver


def _run(cypher, **params):
    with driver().session() as s:
        return [r.data() for r in s.run(cypher, **params)]


def _batches(rows):
    for i in range(0, len(rows), BATCH):
        yield rows[i:i + BATCH]


def project_graph(portal):
    """Make the portal's subgraph equal to the database. Idempotent; other portals are untouched."""
    from django.conf import settings
    if settings.CTXC_ENV == "preprod":
        return "skipped (preprod reads the shared graph, never writes it)"
    for c in SCHEMA:
        _run(c)
    p = portal.domain
    datasets = [{"id": d.dataset_id, "title": d.title} for d in portal.datasets.all()]
    keys = [{"id": f.dataset.dataset_id, "field": f.name, "key": key_of(f.name)}
            for f in Field.objects.filter(dataset__portal=portal, is_key=True).select_related("dataset")]
    edges = [{"src": t.source.dataset_id, "dst": t.target.dataset_id, "kind": t.kind}
             for t in Transformation.objects.filter(target__portal=portal).select_related("source", "target")]
    _run("MATCH (d:Dataset {portal: $p}) WHERE NOT d.dataset_id IN $ids DETACH DELETE d",
         p=p, ids=[d["id"] for d in datasets])
    for rows in _batches(datasets):
        _run("UNWIND $rows AS r MERGE (d:Dataset {portal: $p, dataset_id: r.id}) SET d.title = r.title", p=p, rows=rows)
    _run("MATCH (:Dataset {portal: $p})-[r:HAS_KEY|DERIVED_FROM]->() DELETE r", p=p)
    for rows in _batches(keys):
        _run("""UNWIND $rows AS r MATCH (d:Dataset {portal: $p, dataset_id: r.id}) MERGE (k:Key {name: r.key})
                MERGE (d)-[h:HAS_KEY]->(k) SET h.field = r.field""", p=p, rows=rows)
    for rows in _batches(edges):
        _run("""UNWIND $rows AS r MATCH (s:Dataset {portal: $p, dataset_id: r.src}), (t:Dataset {portal: $p, dataset_id: r.dst})
                MERGE (t)-[e:DERIVED_FROM]->(s) SET e.kind = r.kind""", p=p, rows=rows)
    _run("MATCH (k:Key) WHERE NOT (k)--() DELETE k")
    return {"datasets": len(datasets), "key_links": len(keys), "derived": len(edges)}


def joinable(portal_domain, dataset_id, limit=10):
    """Datasets of the same portal sharing join keys, most shared keys first."""
    return _run("""MATCH (d:Dataset {portal: $p, dataset_id: $id})-[a:HAS_KEY]->(k:Key)<-[b:HAS_KEY]-(o:Dataset {portal: $p})
                   WITH o, collect({key: k.name, here: a.field, there: b.field}) AS on
                   RETURN o.dataset_id AS dataset_id, o.title AS title, on
                   ORDER BY size(on) DESC, o.dataset_id LIMIT $limit""", p=portal_domain, id=dataset_id, limit=limit)


def lineage(portal_domain, dataset_id):
    """upstream: what this dataset is derived from; downstream: what breaks if it changes. Depth <= 5."""
    up = _run("""MATCH path = (:Dataset {portal: $p, dataset_id: $id})-[:DERIVED_FROM*1..5]->(s:Dataset)
                 RETURN DISTINCT s.dataset_id AS dataset_id, min(length(path)) AS depth ORDER BY depth, dataset_id""",
              p=portal_domain, id=dataset_id)
    down = _run("""MATCH path = (t:Dataset)-[:DERIVED_FROM*1..5]->(:Dataset {portal: $p, dataset_id: $id})
                   RETURN DISTINCT t.dataset_id AS dataset_id, min(length(path)) AS depth ORDER BY depth, dataset_id""",
                p=portal_domain, id=dataset_id)
    return {"upstream": up, "downstream": down}


def drop_portal(portal_domain):
    _run("MATCH (d:Dataset {portal: $p}) DETACH DELETE d", p=portal_domain)
    _run("MATCH (k:Key) WHERE NOT (k)--() DELETE k")
