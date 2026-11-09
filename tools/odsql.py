"""Whitelist validator for Explore API v2.1 record queries. Not a full ODSQL parser: it tokenizes and checks that
every bare identifier is a real field of the dataset (or an alias), so an agent cannot guess field names, burn the
client's quota or smuggle other parameters. The API itself stays the second line of defence."""
import difflib
import re

ALLOWED = {"select", "where", "group_by", "order_by", "limit", "offset"}
DEFAULT_LIMIT, MAX_LIMIT, MAX_OFFSET, MAX_LEN = 20, 100, 10_000, 1_000
KEYWORDS = {
    "and", "or", "not", "in", "like", "is", "null", "as", "asc", "desc", "true", "false", "distinct", "between",
    "date", "datetime", "time", "geom",  # literal prefixes: date'2024-01-01'
}
TOKEN = re.compile(r"""
    (?P<ws>\s+)
  | (?P<str>'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")
  | (?P<quoted>`[^`]+`)
  | (?P<ident>\d*[A-Za-z_][A-Za-z0-9_]*)
  | (?P<num>\d+(?:\.\d+)?)
  | (?P<op><=|>=|!=|<>|=|<|>|\+|-|\*|/|%|\(|\)|,)
""", re.X)


class ODSQLRejected(ValueError):
    pass


def tokenize(text):
    pos, out = 0, []
    while pos < len(text):
        m = TOKEN.match(text, pos)
        if not m:
            raise ODSQLRejected(f"unexpected character {text[pos]!r} at {pos}")
        if m.lastgroup != "ws":
            out.append((m.lastgroup, m.group()))
        pos = m.end()
    for (_, a), (_, b) in zip(out, out[1:]):
        if (a, b) in (("-", "-"), ("/", "*")):
            raise ODSQLRejected("comments are not allowed")
    return out


def _aliases(select):
    toks = tokenize(select or "")
    return {b.strip("`") for (k, a), (_, b) in zip(toks, toks[1:]) if k == "ident" and a.lower() == "as"}


def _check(text, fields, aliases, param):
    toks = tokenize(text)
    for i, (kind, value) in enumerate(toks):
        if kind not in ("ident", "quoted"):
            continue
        name = value.strip("`")
        nxt = toks[i + 1] if i + 1 < len(toks) else (None, None)
        if kind == "ident" and (name.lower() in KEYWORDS or nxt[1] == "("):
            continue  # keyword, literal prefix or function call
        if name not in fields and name not in aliases:
            close = difflib.get_close_matches(name, sorted(fields), n=3, cutoff=0.6)
            hint = f"; similar fields: {', '.join(close)}" if close else ""
            raise ODSQLRejected(f"unknown field in {param}: {name}{hint}")


def validate(fields, params):
    """Return cleaned params for /records or raise ODSQLRejected with a message an agent can act on."""
    fields = set(fields)
    extra = set(params) - ALLOWED
    if extra:
        raise ODSQLRejected(f"parameters not allowed: {', '.join(sorted(extra))}")
    out = {}
    aliases = _aliases(params.get("select"))
    for p in ("select", "where", "group_by", "order_by"):
        v = params.get(p)
        if v in (None, ""):
            continue
        if not isinstance(v, str):
            raise ODSQLRejected(f"{p} must be a string")
        if len(v) > MAX_LEN:
            raise ODSQLRejected(f"{p} longer than {MAX_LEN} characters")
        if p == "select" and v.strip() == "*":
            out[p] = v
            continue
        _check(v, fields, aliases, p)
        out[p] = v
    try:
        out["limit"] = min(int(params.get("limit", DEFAULT_LIMIT)), MAX_LIMIT)
        out["offset"] = int(params.get("offset", 0))
    except (TypeError, ValueError):
        raise ODSQLRejected("limit and offset must be integers") from None
    if out["limit"] < 0 or not 0 <= out["offset"] <= MAX_OFFSET:
        raise ODSQLRejected(f"limit >= 0 and 0 <= offset <= {MAX_OFFSET}")
    return out
