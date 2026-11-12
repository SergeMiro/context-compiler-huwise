"""The only place that talks to a model. Any OpenAI-compatible /chat/completions endpoint; models are configuration,
never code: primary CTXC_LLM_{BASE_URL,API_KEY,MODEL,NAME}, optional backup CTXC_LLM2_* (another provider, its own
limits). `using(name)` picks one for the current call chain; with fallback on, a 429 or an outage of one provider moves
the call to the other. Evals turn fallback off so a run measures one model. FakeLLM replays a script for tests."""
import contextlib
import contextvars
import json
import logging
import time

import httpx
from django.conf import settings

log = logging.getLogger(__name__)
RETRY_STATUS = {429, 500, 502, 503, 504}
ATTEMPTS = 6  # free models answer 429/503 in bursts: 2+4+8+16+32 s of backoff before giving up
_sleep = time.sleep
_choice = contextvars.ContextVar("llm_provider", default=(None, False))  # (provider name or None = primary, fallback)


class LLMNotConfigured(RuntimeError):
    pass


def providers():
    """{name: {"base", "key", "model"}} for every fully configured endpoint, primary first. Keys never leave here."""
    out = {}
    for pre, default in (("CTXC_LLM", "primary"), ("CTXC_LLM2", "backup")):
        base, key, model = (getattr(settings, f"{pre}_{k}", "") for k in ("BASE_URL", "API_KEY", "MODEL"))
        if base and key and model:
            out[getattr(settings, f"{pre}_NAME", "") or default] = {"base": base, "key": key, "model": model}
    return out


def public_providers():
    return [{"name": n, "model": p["model"]} for n, p in providers().items()]


@contextlib.contextmanager
def using(name=None, fallback=False):
    if name and name not in providers():
        raise LLMNotConfigured(f"unknown provider {name!r}")
    token = _choice.set((name, fallback))
    try:
        yield
    finally:
        _choice.reset(token)


def _order():
    provs = providers()
    if not provs:
        raise LLMNotConfigured("set CTXC_LLM_BASE_URL, CTXC_LLM_API_KEY and CTXC_LLM_MODEL in .env")
    name, fallback = _choice.get()
    first = name or next(iter(provs))
    rest = [n for n in provs if n != first] if fallback else []
    return [(n, provs[n]) for n in [first, *rest]]


def model_name():
    try:
        return _order()[0][1]["model"]
    except LLMNotConfigured:
        return "not-configured"


def _post(c, p, body):
    """-> (response or None, transport error or None) after this provider's own retries."""
    body = body | {"model": p["model"]}
    r = None
    for attempt in range(ATTEMPTS):
        try:
            r = c.post(f"{p['base'].rstrip('/')}/chat/completions", json=body, headers={"Authorization": f"Bearer {p['key']}"})
        except httpx.TransportError as e:
            if attempt == ATTEMPTS - 1:
                return None, e
        else:
            if r.status_code not in RETRY_STATUS or attempt == ATTEMPTS - 1:
                return r, None
            if r.status_code == 429 and len(_order()) > 1:  # rate limit: the other provider has its own, go now
                return r, None
        _sleep(2 ** (attempt + 1))
    return r, None


def chat(messages, tools=None, temperature=0, transport=None):
    """-> {"message": {"role", "content", "tool_calls"}, "tokens", "ms", "model", "provider"}"""
    body = {"messages": messages, "temperature": temperature}
    if tools:
        body["tools"] = tools
    t0 = time.monotonic()
    order = _order()
    with httpx.Client(timeout=settings.CTXC_LLM_TIMEOUT, transport=transport) as c:
        for i, (name, p) in enumerate(order):
            r, err = _post(c, p, body)
            failed = err is not None or r.status_code in RETRY_STATUS
            if failed and i < len(order) - 1:
                log.warning("llm provider=%s failed (%s), falling back to %s", name, err or r.status_code, order[i + 1][0])
                continue
            if err is not None:
                raise err
            r.raise_for_status()
            break
    data = r.json()
    msg = data["choices"][0]["message"]
    tokens = (data.get("usage") or {}).get("total_tokens", 0)
    ms = int((time.monotonic() - t0) * 1000)
    log.info("llm provider=%s model=%s tokens=%s ms=%s", name, p["model"], tokens, ms)  # never the messages
    return {"message": {"role": "assistant", "content": msg.get("content"), "tool_calls": msg.get("tool_calls") or []},
            "tokens": tokens, "ms": ms, "model": p["model"], "provider": name}


class FakeLLM:
    """Replays answers in order. An item is a str (final text) or a list of (tool_name, arguments) tool calls."""

    def __init__(self, script):
        self.script, self.calls = list(script), []

    def __call__(self, messages, tools=None, temperature=0):
        self.calls.append(messages)
        item = self.script.pop(0) if self.script else "pas de données"
        if isinstance(item, str):
            msg = {"role": "assistant", "content": item, "tool_calls": []}
        else:
            msg = {"role": "assistant", "content": None, "tool_calls": [
                {"id": f"call_{len(self.calls)}_{i}", "type": "function",
                 "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}
                for i, (name, args) in enumerate(item)]}
        return {"message": msg, "tokens": 0, "ms": 0}
