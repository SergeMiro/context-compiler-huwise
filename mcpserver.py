"""MCP server (streamable HTTP) over tools/. Portal from the X-Domain header (as Huwise's MCP), else the `portal`
argument. X-Apikey goes through to the Explore API and is never stored or logged."""
import json
import logging
import os
import threading
import time

from django.db import close_old_connections
from mcp.server.mcpserver import Context, MCPServer
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response

import tools

RATE, BURST = 10.0, 20  # calls per second per portal
_buckets, _lock = {}, threading.Lock()

server = MCPServer(
    "context-compiler",
    instructions="Find a dataset, read its card, then query it. Cards tell you value formats (codes keep leading "
                 "zeros), join keys and freshness. Answer only from query results.",
)


def resolve_portal(headers, portal_arg):
    headers = {k.lower(): v for k, v in (headers or {}).items()}
    return headers.get("x-domain") or portal_arg, headers.get("x-apikey")


def _allow(portal):
    # shortcut: in-memory token bucket per process; move to a shared counter when running several servers
    with _lock:
        tokens, last = _buckets.get(portal, (BURST, time.monotonic()))
        now = time.monotonic()
        tokens = min(BURST, tokens + (now - last) * RATE)
        ok = tokens >= 1
        _buckets[portal] = (tokens - 1 if ok else tokens, now)
        return ok


def _call(ctx, portal, fn, *args, **kwargs):
    domain, key = resolve_portal(ctx.headers if ctx else None, portal)
    if not domain:
        return {"error": "no portal: send the X-Domain header or the portal argument"}
    if not _allow(domain):
        return {"error": "rate limited: max 10 calls per second per portal"}
    if fn is tools.query:
        kwargs["api_key"] = key
    close_old_connections()  # tools run in a worker thread: drop connections MariaDB has timed out
    return fn(domain, *args, **kwargs)


@server.tool()
def find_dataset(question: str, ctx: Context, portal: str = "", k: int = 5) -> dict:
    """Search the portal for datasets that can answer the question. Returns short cards, best first."""
    return _call(ctx, portal, tools.find_dataset, question, k=k)


@server.tool()
def explain_dataset(dataset_id: str, ctx: Context, portal: str = "") -> dict:
    """Full card of one dataset: every field with type and example values, query templates, notes, joinable
    datasets (shared keys) and lineage."""
    return _call(ctx, portal, tools.explain_dataset, dataset_id)


@server.tool()
def query(dataset_id: str, ctx: Context, select: str = "", where: str = "", group_by: str = "",
          order_by: str = "", limit: int = 20, portal: str = "") -> dict:
    """Run an ODSQL query on a dataset's records (read-only, limit <= 100). Only real field names are accepted.
    To count rows use limit=0 and read total_count; with an aggregate (count(distinct), sum, group_by) use limit >= 1."""
    params = {k: v for k, v in dict(select=select, where=where, group_by=group_by, order_by=order_by).items() if v}
    params["limit"] = limit
    return _call(ctx, portal, tools.query, dataset_id, params)


# --- read-only JSON API for the static showcase (same tools as MCP, one portal, same rate limit) ---

log = logging.getLogger(__name__)
DEMO_PORTAL = os.environ.get("CTXC_DEMO_PORTAL", "data.education.gouv.fr")
_QUERY_KEYS = ("select", "where", "group_by", "order_by")


def api_call(kind, args):
    """kind: find | explain | query (validated) | raw (generic pass-through, the "naked" baseline). -> (status, body)"""
    def arg(k, n=300):
        return (args.get(k) or "").strip()[:n]

    if kind == "find":
        q = arg("q")
        return (200, tools.find_dataset(DEMO_PORTAL, q, k=5)) if q else (400, {"error": "q is required"})
    dataset_id = arg("id", 200)
    if not dataset_id:
        return 400, {"error": "id is required"}
    if kind == "explain":
        return 200, tools.explain_dataset(DEMO_PORTAL, dataset_id)
    params = {k: arg(k, 1000) for k in _QUERY_KEYS if arg(k)}
    try:
        params["limit"] = max(0, min(int(arg("limit") or 20), 100))
    except ValueError:
        return 400, {"error": "limit must be an integer"}
    fn = tools.query if kind == "query" else tools.naked_query
    return 200, fn(DEMO_PORTAL, dataset_id, params)


def _route(kind):
    async def handler(request):
        def run():
            close_old_connections()
            if not _allow(DEMO_PORTAL):
                return 429, {"error": "rate limited: max 10 calls per second"}
            try:
                args = dict(request.query_params)
                if kind == "demo/run":
                    return demo_run(args)
                return live_agent(args) if kind == "agent" else api_call(kind, args)
            except Exception:  # upstream timeout, ES down: a clean JSON error for the page, details in the log
                log.exception("api %s failed", kind)
                return 502, {"error": "upstream error, try again"}
        status, body = await run_in_threadpool(run)
        return Response(json.dumps(body, ensure_ascii=False, default=str), status_code=status,
                        media_type="application/json", headers={"Cache-Control": "no-store"})
    return handler


# Live agent duel on golden questions only (they can be scored). Costs model calls: capped per day, cached for an hour,
# at most 2 agents at once. The MCP tools above never call a model.
LIVE_RUNS_PER_DAY = int(os.environ.get("CTXC_LIVE_RUNS_PER_DAY", "40"))
LIVE_CACHE_S = 3600
_live = {"day": None, "runs": 0, "cache": {}}
_live_slots = threading.Semaphore(2)


def live_agent(args):
    import datetime

    import llm
    from evals.agent import run_agent
    from evals.models import EvalCase
    from evals.runner import public_row, score
    mode, slug = (args.get("mode") or ""), (args.get("slug") or "")[:100]
    if mode not in ("naked", "compiled"):
        return 400, {"error": "mode must be naked or compiled"}
    case = EvalCase.objects.filter(portal__domain=DEMO_PORTAL, slug=slug).first()
    if case is None:
        return 404, {"error": "unknown question"}
    with _lock:
        hit = _live["cache"].get((slug, mode))
        if hit and time.monotonic() - hit[0] < LIVE_CACHE_S:
            return 200, hit[1] | {"cached_s": int(time.monotonic() - hit[0])}
        today = datetime.date.today()
        if _live["day"] != today:
            _live.update(day=today, runs=0)
        if _live["runs"] >= LIVE_RUNS_PER_DAY:
            return 429, {"error": "daily live quota used up"}
        _live["runs"] += 1
    if not _live_slots.acquire(timeout=120):
        return 503, {"error": "busy, try again"}
    try:
        row = public_row(score(case, run_agent(DEMO_PORTAL, case.question, mode)))
    except llm.LLMNotConfigured:
        return 503, {"error": "no model configured"}
    finally:
        _live_slots.release()
    body = row | {"model": llm.model_name()}
    with _lock:
        _live["cache"][(slug, mode)] = (time.monotonic(), body)
    return 200, body


def demo_run(args):
    """Live run of one configuration (A huwise / 0 naked / B compiled / C optimized) on a scenario question, with the
    model the page picked (`provider`; a 429 there falls back to the other provider, and the answer says which model
    answered). C on a FAST route needs no model and is not counted. Model runs share the live daily cap and cache."""
    import datetime

    import llm
    from evals.runner import _run_once
    from optimizer import pipeline, router
    from optimizer.management.commands.record_traces import expected, public
    from optimizer.scenarios import BY_ID
    s = BY_ID.get((args.get("scenario") or "")[:40])
    if s is None or s["kind"] != "recorded":
        return 404, {"error": "unknown scenario (simulated scenarios are not run live)"}
    mode, provider = args.get("mode") or "optimized", args.get("provider") or None
    if mode not in ("huwise", "naked", "compiled", "optimized"):
        return 400, {"error": "mode must be huwise, naked, compiled or optimized"}
    if provider and provider not in llm.providers():
        return 400, {"error": "unknown provider"}
    if mode == "huwise" and not os.environ.get("HUWISE_API_KEY"):
        return 503, {"error": "A needs a Huwise portal API key on this server: recorded trace only"}
    q = s["question"]
    if mode == "optimized" and router.route(DEMO_PORTAL, q)["route"] == "FAST":
        res = pipeline.answer(DEMO_PORTAL, q)
        return 200, public(res, q, expected(DEMO_PORTAL, s.get("ref"))) | {"models": []}
    key = ("demo", s["id"], mode, provider)
    with _lock:
        hit = _live["cache"].get(key)
        if hit and time.monotonic() - hit[0] < LIVE_CACHE_S:
            return 200, hit[1] | {"cached_s": int(time.monotonic() - hit[0])}
        today = datetime.date.today()
        if _live["day"] != today:
            _live.update(day=today, runs=0)
        if _live["runs"] >= LIVE_RUNS_PER_DAY:
            return 429, {"error": "daily live quota used up: recorded trace only"}
        _live["runs"] += 1
    if not _live_slots.acquire(timeout=120):
        return 503, {"error": "busy, try again"}
    try:
        with llm.using(provider, fallback=True):
            res = _run_once(DEMO_PORTAL, q, mode, None)
    except llm.LLMNotConfigured:
        return 503, {"error": "no model configured"}
    finally:
        _live_slots.release()
    body = public(res, q, expected(DEMO_PORTAL, s.get("ref"))) | {"models": sorted({x["model"] for x in res["spans"] if x.get("model")})}
    with _lock:
        _live["cache"][key] = (time.monotonic(), body)
    return 200, body


for _kind in ("find", "explain", "query", "raw", "agent", "demo/run"):
    server.custom_route(f"/api/{_kind}", methods=["GET"])(_route(_kind))

