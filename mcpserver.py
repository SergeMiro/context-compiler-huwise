"""MCP server (streamable HTTP) over tools/. Portal from the X-Domain header (as Huwise's MCP), else the `portal`
argument. X-Apikey goes through to the Explore API and is never stored or logged."""
import threading
import time

from django.db import close_old_connections
from mcp.server.mcpserver import Context, MCPServer

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
