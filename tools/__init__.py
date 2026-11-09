"""Hot path: the three tools agents call. No LLM, no writes except the ToolCall log.
The MCP server and the eval agent call exactly these functions. `naked_*` = generic catalog access for comparison."""
import difflib
import functools
import time

import httpx

from catalog.models import Dataset, Portal
from ctx.compile import current
from ctx.models import ToolCall
from projections import es, graph

from .odsql import ALLOWED, MAX_LIMIT, ODSQLRejected, validate

_http = httpx.Client(timeout=10, follow_redirects=True)


class ToolError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _portal(domain):
    try:
        return Portal.objects.get(domain=domain)
    except Portal.DoesNotExist:
        raise ToolError("unknown_portal", f"unknown portal: {domain}") from None


def _dataset(portal, dataset_id):
    ds = Dataset.objects.filter(portal=portal, dataset_id=dataset_id).first()
    if ds is None:
        ids = list(Dataset.objects.filter(portal=portal).values_list("dataset_id", flat=True))
        close = difflib.get_close_matches(dataset_id, ids, n=3, cutoff=0.5)
        raise ToolError("unknown_dataset", f"unknown dataset: {dataset_id}" + (f"; similar: {', '.join(close)}" if close else ""))
    return ds


def tool(name):
    """Log every call (tool, ms, ok, error code — never the question, query or key); errors become {'error': ...}."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(portal_domain, *args, **kwargs):
            t0, code = time.monotonic(), ""
            try:
                portal = _portal(portal_domain)
            except ToolError as e:
                return {"error": str(e)}
            try:
                return fn(portal, *args, **kwargs)
            except ToolError as e:
                code = e.code
                return {"error": str(e)}
            except ODSQLRejected as e:
                code = "odsql_rejected"
                return {"error": f"query rejected: {e}"}
            except Exception:
                code = "internal"
                raise
            finally:
                ToolCall.objects.create(portal=portal, tool=name, ms=int((time.monotonic() - t0) * 1000),
                                        ok=not code, error_code=code)
        return wrapper
    return deco


@functools.lru_cache(maxsize=4096)
def _full_card(dataset_pk, version):
    # shortcut: per-process cache keyed by card version (new version = new key); shared cache with >1 server
    from ctx.models import Card
    return Card.objects.get(dataset_id=dataset_pk, version=version).full


@tool("find_dataset")
def find_dataset(portal, question, k=5):
    hits = es.search(portal.domain, question, k=min(int(k), 10))
    return {"results": [{"dataset_id": h["dataset_id"], "card": h["short"]} for h in hits],
            "next": "explain_dataset(dataset_id) for fields, value formats and joins; then query(...)"}


@tool("explain_dataset")
def explain_dataset(portal, dataset_id):
    ds = _dataset(portal, dataset_id)
    card = current(ds)
    if card is None:
        raise ToolError("not_compiled", f"{dataset_id} has no compiled card yet")
    return {"dataset_id": ds.dataset_id, "card": _full_card(ds.pk, card.version),
            "joinable": [{"dataset_id": j["dataset_id"], "on": sorted({o["key"] for o in j["on"]})}
                         for j in graph.joinable(portal.domain, ds.dataset_id, limit=8)],
            "lineage": graph.lineage(portal.domain, ds.dataset_id)}


def _records(portal, dataset_id, params, api_key):
    headers = {"Authorization": f"Apikey {api_key}"} if api_key else {}
    r = _http.get(f"https://{portal.domain}/api/explore/v2.1/catalog/datasets/{dataset_id}/records",
                  params=params, headers=headers)
    if r.status_code == 400:
        body = r.json()
        raise ToolError(body.get("error_code", "api_400"), f"API: {body.get('message', r.text)[:500]}")
    if r.status_code in (401, 403):
        raise ToolError("forbidden", "API refused access to this dataset (API key missing or not allowed)")
    r.raise_for_status()
    body = r.json()
    return {"total_count": body.get("total_count"), "results": body.get("results", [])}


@tool("query")
def query(portal, dataset_id, params, api_key=None):
    ds = _dataset(portal, dataset_id)
    clean = validate(ds.fields.values_list("name", flat=True), params or {})
    return _records(portal, ds.dataset_id, clean, api_key)


# --- generic access, as a catalog-wide MCP server gives it (baseline for evals) ---

@tool("naked_search")
def naked_search(portal, question, k=5):
    hits = es.search(portal.domain, question, k=min(int(k), 10), naked=True)
    return {"results": [{"dataset_id": h["dataset_id"], "title": h["title"], "description": h["description"][:300]}
                        for h in hits]}


@tool("naked_get")
def naked_get(portal, dataset_id):
    ds = _dataset(portal, dataset_id)
    m = ds.raw_metas
    return {"dataset_id": ds.dataset_id, "title": ds.title, "description": ds.description[:1500],
            "records_count": ds.records_count, "modified": m.get("modified"), "keywords": ds.keywords,
            "fields": [{"name": f.name, "type": f.type, "label": f.label, "description": f.description}
                       for f in ds.fields.all()],
            "examples": _records(portal, ds.dataset_id, {"limit": 3}, None)["results"]}


@tool("naked_query")
def naked_query(portal, dataset_id, params, api_key=None):
    ds = _dataset(portal, dataset_id)
    params = {k: v for k, v in (params or {}).items() if k in ALLOWED}
    params["limit"] = min(int(params.get("limit", 20)), MAX_LIMIT)
    return _records(portal, ds.dataset_id, params, api_key)
