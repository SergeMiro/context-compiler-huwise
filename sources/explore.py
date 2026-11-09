"""Huwise / Opendatasoft Explore API v2.1 -> Portal / Dataset / Field. Knows HTTP and models, nothing else."""
import logging
import re
import time
from datetime import datetime
from html.parser import HTMLParser

import httpx
from django.conf import settings
from django.db import transaction
from django.utils.dateparse import parse_datetime

from catalog.models import Dataset, Field, Portal

from .keys import is_pii, key_of

log = logging.getLogger(__name__)
SAMPLES = 10


class BudgetExhausted(RuntimeError):
    pass


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in ("p", "br", "li", "div"):
            self.parts.append(" ")


def html_to_text(html, limit=4000):
    if not html:
        return ""
    p = _Text()
    p.feed(html)
    return re.sub(r"\s+", " ", "".join(p.parts)).strip()[:limit]


class ExploreSource:
    def __init__(self, domain, api_key=None, transport=None):
        headers = {"Authorization": f"Apikey {api_key}"} if api_key else {}
        self.client = httpx.Client(base_url=f"https://{domain}/api/explore/v2.1", headers=headers,
                                   timeout=30, transport=transport, follow_redirects=True)
        self.requests = 0
        self.limit = self.remaining = None

    def get(self, path, **params):
        r = self.client.get(path, params=params)
        self.requests += 1
        if "x-ratelimit-limit" in r.headers:
            self.limit = int(r.headers["x-ratelimit-limit"])
            self.remaining = int(r.headers["x-ratelimit-remaining"])
        r.raise_for_status()
        return r.json()

    def full(self):
        """Whole catalog in one request (314 datasets / 527 KB / ~1 s on data.education.gouv.fr)."""
        return self.get("/catalog/exports/json")

    def since(self, cursor):
        """Datasets modified after `cursor`. The API compares `modified` by day, so filter the rest here."""
        out, offset = [], 0
        while True:
            page = self.get("/catalog/datasets", where=f"modified >= date'{cursor.date().isoformat()}'",
                            order_by="modified asc", limit=100, offset=offset)
            out += page["results"]
            offset += 100
            if offset >= page["total_count"]:
                break
        return [d for d in out if _modified(d) and _modified(d) > cursor]

    def facets(self, dataset_id):
        """All facet (categorical) fields with value counts in one request."""
        return self.get(f"/catalog/datasets/{dataset_id}/facets")["facets"]


def _metas(item):
    return item["metas"]["default"]


def _modified(item):
    m = _metas(item).get("modified")
    return parse_datetime(m) if m else None


def _upsert(portal, item):
    """One dataset and its fields in one transaction. Returns (dataset, created, changed)."""
    m = _metas(item)
    values = dict(
        title=(m.get("title") or item["dataset_id"])[:500], description=html_to_text(m.get("description")),
        themes=m.get("theme") or [], keywords=m.get("keyword") or [], license=(m.get("license") or "")[:300],
        publisher=(m.get("publisher") or "")[:300], update_frequency=m.get("update_frequency") or "",
        records_count=m.get("records_count") or 0, modified=_modified(item), federated=bool(m.get("federated")),
        source_domain=m.get("source_domain") or "", source_dataset=m.get("source_dataset") or "", raw_metas=m,
    )
    with transaction.atomic():
        ds = Dataset.objects.filter(portal=portal, dataset_id=item["dataset_id"]).first()
        created = ds is None
        changed = created or ds.modified != values["modified"]
        if created:
            ds = Dataset.objects.create(portal=portal, dataset_id=item["dataset_id"], **values)
        else:
            for k, v in values.items():
                setattr(ds, k, v)
            ds.save()
        existing = {f.name: f for f in ds.fields.all()}
        new, upd, seen = [], [], set()
        for pos, f in enumerate(item.get("fields") or []):
            seen.add(f["name"])
            attrs = dict(position=pos, label=(f.get("label") or "")[:500], type=f.get("type") or "",
                         description=f.get("description") or "", is_key=key_of(f["name"]) is not None,
                         is_pii=is_pii(f["name"]))
            if f["name"] in existing:
                obj = existing[f["name"]]
                for k, v in attrs.items():
                    setattr(obj, k, v)
                upd.append(obj)
            else:
                new.append(Field(dataset=ds, name=f["name"], **attrs))
        Field.objects.bulk_create(new)
        if upd:
            Field.objects.bulk_update(upd, ["position", "label", "type", "description", "is_key", "is_pii"])
        ds.fields.exclude(name__in=seen).delete()
    return ds, created, changed


def _samples(src, ds, budget):
    """Top values of facet fields; never for PII fields."""
    if src.requests >= budget or (src.limit and src.remaining is not None and src.remaining < src.limit * 0.1):
        raise BudgetExhausted(f"{src.requests} requests, remaining {src.remaining}/{src.limit}")
    by_name = {f.name: f for f in ds.fields.all()}
    if not any("facet" in (f.get("annotations") or {}) for f in ds.raw_fields):
        ds.samples_for = ds.modified
        ds.save(update_fields=["samples_for"])
        return False  # no categorical fields declared: nothing to sample, save the request
    upd = []
    for facet in src.facets(ds.dataset_id):
        f = by_name.get(facet["name"])
        if f is None or f.is_pii:
            continue
        top = sorted(facet["facets"], key=lambda v: -v["count"])[:SAMPLES]
        f.sample_values = [v["value"] for v in top]
        upd.append(f)
    Field.objects.bulk_update(upd, ["sample_values"])
    ds.samples_for = ds.modified
    ds.save(update_fields=["samples_for"])
    return True


def scan(portal, full=False, samples=True, transport=None, api_key=None):
    t0 = time.monotonic()
    src = ExploreSource(portal.domain, api_key=api_key, transport=transport)
    full = full or portal.scan_cursor is None
    items = src.full() if full else src.since(portal.scan_cursor)
    stats = {"mode": "full" if full else "incremental", "created": 0, "updated": 0, "deleted": 0,
             "fields": 0, "samples": 0, "samples_failed": 0, "budget_stop": ""}
    changed = []
    for item in items:
        ds, created, ch = _upsert(portal, item)
        stats["created" if created else "updated"] += int(created or ch)
        stats["fields"] += len(item.get("fields") or [])
        if ds.samples_for != ds.modified:  # changed, or samples never taken / failed last time
            ds.raw_fields = item.get("fields") or []
            changed.append(ds)
    if full:
        ids = {i["dataset_id"] for i in items}
        stats["deleted"], _ = portal.datasets.exclude(dataset_id__in=ids).delete()
    if samples:
        budget = (src.limit or 50000) * settings.CTXC_SCAN_BUDGET_PCT // 100
        try:
            for ds in changed:
                try:
                    stats["samples"] += _samples(src, ds, budget)
                except httpx.HTTPStatusError as e:
                    if not 400 <= e.response.status_code < 500 or e.response.status_code == 429:
                        raise
                    # e.g. a federated dataset whose source domain is gone: skip it, keep scanning
                    stats["samples_failed"] += 1
                    log.warning("scan %s: no facets for %s: %s", portal.domain, ds.dataset_id, e.response.status_code)
        except BudgetExhausted as e:
            stats["budget_stop"] = str(e)
            log.warning("scan %s: sample budget exhausted: %s", portal.domain, e)
    mods = [m for m in (_modified(i) for i in items) if m]
    if mods and (portal.scan_cursor is None or max(mods) > portal.scan_cursor):
        portal.scan_cursor = max(mods)  # moved only after everything above succeeded
        portal.save(update_fields=["scan_cursor"])
    stats.update(datasets=portal.datasets.count(), requests=src.requests, seconds=round(time.monotonic() - t0, 1))
    return stats
