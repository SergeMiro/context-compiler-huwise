"""Configuration A for real: the agent gets the actual Huwise MCP server's tools (https://mcp.huwise.com/mcp),
with their own names, descriptions and schemas as `tools/list` returns them. Needs a portal API key in
HUWISE_API_KEY (read-only key of a plain user account); the key goes only into the request headers."""
import functools
import json
import os

import httpx

URL = "https://mcp.huwise.com/mcp"
_http = httpx.Client(timeout=60)


def _rpc(domain, method, params=None):
    key = os.environ.get("HUWISE_API_KEY")
    if not key:
        raise RuntimeError("HUWISE_API_KEY is not set: the real Huwise MCP baseline needs a portal API key")
    r = _http.post(URL, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
                   headers={"Accept": "application/json, text/event-stream", "X-Domain": f"https://{domain}",
                            "X-Apikey": key})
    r.raise_for_status()
    text = r.text
    if text.lstrip().startswith("event:") or "\ndata:" in text or text.startswith("data:"):  # SSE framing
        text = next(line[5:] for line in text.splitlines() if line.startswith("data:"))
    body = json.loads(text)
    if "error" in body:
        raise RuntimeError(f"Huwise MCP {method}: {body['error']}")
    return body["result"]


@functools.lru_cache(maxsize=None)
def specs(domain):
    """OpenAI-style function specs from the server's own tool list; `url` is filled by us (it is the portal)."""
    out = []
    for t in _rpc(domain, "tools/list")["tools"]:
        schema = json.loads(json.dumps(t["inputSchema"]))
        schema.get("properties", {}).pop("url", None)
        schema["required"] = [r for r in schema.get("required", []) if r != "url"]
        out.append({"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                     "parameters": schema}})
    return tuple(json.dumps(s) for s in out)  # hashable for the cache


def call(domain, name, args):
    res = _rpc(domain, "tools/call", {"name": name, "arguments": {**args, "url": f"https://{domain}"}})
    text = "".join(c.get("text", "") for c in res.get("content", []))
    if res.get("isError"):
        return {"error": text[:1000]}
    data = (res.get("structuredContent") or {}).get("result")
    if data is None:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {"text": text}
    return data if isinstance(data, dict) else {"result": data}


def toolset(domain):
    return {s["function"]["name"]: (s, functools.partial(lambda n, d, a: call(d, n, a), s["function"]["name"]))
            for s in map(json.loads, specs(domain))}
