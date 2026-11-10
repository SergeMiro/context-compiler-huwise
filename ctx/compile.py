"""Dataset + fields + kept edits -> Card (short for search results, full for explain). Deterministic, no LLM."""
import hashlib
import re

from catalog.models import Dataset
from ctx.models import Card, ContextEdit

SHORT_BUDGET, FULL_BUDGET = 400, 1500
SHORT_FIELDS = 12
LOW_PRIORITY_TYPES = {"geo_shape", "geo_point_2d", "file", "json_blob"}
# the apostrophe and limit=0 lines come from eval transcripts: 'COTE-D''OR' is a syntax error, and an aggregate
# with limit=0 returns no rows
LIMITS = ("records: limit <= 100 per call; to count rows use limit=0 and read total_count, but with an aggregate "
          "(count(distinct …), sum, avg, group_by) use limit >= 1; string literals in single quotes, a value with an "
          "apostrophe in double quotes: \"COTE D'OR\"; codes are text: keep leading zeros; to filter by place "
          "prefer code_* fields over labels; no DISTINCT: list values with group_by; a field name that starts with a digit "
          "goes in backticks: `2ndes_gt_filles`.")


def tokens(text):
    # shortcut: ~4 chars per token for French/English; swap for the chosen model's tokenizer if budgets get tight
    return len(text) // 4


def _first_sentences(text, max_chars=300):
    out = ""
    for s in re.split(r"(?<=[.!?])\s+", text):
        if out and len(out) + len(s) > max_chars:
            break
        out = f"{out} {s}".strip()
    return out[:max_chars]


def _q(v):
    return f"'{v}'" if isinstance(v, str) else str(v)


def _label(f):
    same = re.sub(r"[\W_]+", "", f.label).lower() == re.sub(r"[\W_]+", "", f.name).lower()
    return "" if not f.label or same else f.label


def _edits(ds, extra=None):
    kept = list(ds.edits.filter(status="kept").order_by("created_at", "id"))
    if extra is not None and extra not in kept:
        kept.append(extra)  # preview: the card as it would be with this edit
    desc = [e.after for e in kept if e.kind == "description"]
    return {
        "description": desc[-1] if desc else None,
        "synonyms": [s.strip() for e in kept if e.kind == "synonyms" for s in e.after.split(",") if s.strip()],
        "query_template": [e.after.strip() for e in kept if e.kind == "query_template"],
        "note": [e.after.strip() for e in kept if e.kind == "note"],
    }


def _ordered_fields(fields, edits):
    mentioned = " ".join(edits["query_template"] + edits["note"])
    def prio(f):
        if f.is_key:
            return 0
        if re.search(rf"\b{re.escape(f.name)}\b", mentioned):
            return 1
        return 3 if f.is_pii or f.type in LOW_PRIORITY_TYPES else 2
    return sorted(fields, key=lambda f: (prio(f), f.position))


def _fit(head, lines, tail, budget, more):
    """Add lines while the card stays within budget; say how many were left out."""
    used, kept = tokens("\n".join(head + tail)), []
    for i, line in enumerate(lines):
        if used + tokens(line) + 12 > budget:
            return head + kept + [more.format(n=len(lines) - i)] + tail
        kept.append(line)
        used += tokens(line) + 1
    return head + kept + tail


def render(ds, extra=None):
    fields = list(ds.fields.all())
    edits = _edits(ds, extra)
    fields_by_prio = _ordered_fields(fields, edits)
    description = edits["description"] or ds.description
    updated = ds.modified.strftime("%d.%m.%Y") if ds.modified else "?"
    facts = " · ".join(x for x in (f"{ds.records_count} rows", f"updated {updated}"
                                   + (f" ({ds.update_frequency.lower()})" if ds.update_frequency else ""),
                                   ds.license, ds.publisher) if x)
    keys = ", ".join(f.name + (f" (e.g. {_q(f.sample_values[0])})" if f.sample_values else "")
                     for f in fields_by_prio if f.is_key)
    head = [f"## {ds.dataset_id} — {ds.title}", _first_sentences(description), facts]
    if keys:
        head.append(f"Keys: {keys}")
    names = [f.name + (f" ({_label(f)})" if _label(f) else "") for f in fields_by_prio if not f.is_key]
    head.append("Fields: " + ", ".join(names[:SHORT_FIELDS]) + (f", … +{len(names) - SHORT_FIELDS}" if len(names) > SHORT_FIELDS else ""))
    if edits["synonyms"]:
        head.append("Also known as: " + ", ".join(edits["synonyms"]))
    short = "\n".join(_fit(head, [], [], SHORT_BUDGET, ""))
    if tokens(short) > SHORT_BUDGET:  # pathological titles/descriptions: hard cut
        short = short[: SHORT_BUDGET * 4]

    full_head = [f"## {ds.dataset_id} — {ds.title}", description[:1200], facts]
    if ds.themes or ds.keywords:
        full_head.append("Themes: " + ", ".join(ds.themes + ds.keywords))
    if edits["synonyms"]:
        full_head.append("Also known as: " + ", ".join(edits["synonyms"]))
    tail = []
    if edits["query_template"]:
        tail += ["### Query templates"] + [f"- {t}" for t in edits["query_template"]]
    if edits["note"]:
        tail += ["### Notes"] + [f"- {n}" for n in edits["note"]]
    tail += ["### Limits", f"- {LIMITS}"]
    field_lines = []
    for f in fields_by_prio:
        line = f"- {f.name} · {f.type}" + (" · key" if f.is_key else "")
        extra = " — ".join(x for x in (_label(f), (f.description or "")[:160]) if x)
        if extra:
            line += f" · {extra}"
        if f.sample_values and not f.is_pii:
            line += " · e.g. " + ", ".join(_q(str(v)[:40]) for v in f.sample_values[:5])
        if f.type in ("date", "datetime"):
            # years stored as dates: session='2025' is a type error on the API, year(session)=2025 works
            line += f" · filter by year: year({f.name})=2025"
        field_lines.append(line)
    full = "\n".join(_fit(full_head + ["### Fields"], field_lines, tail, FULL_BUDGET,
                          "- … {n} more fields not shown"))
    return short, full


def compile_dataset(ds):
    """New Card version if the rendered text changed, else None."""
    short, full = render(ds)
    h = hashlib.sha256(f"{short}\n\x00\n{full}".encode()).hexdigest()
    last = ds.cards.order_by("-version").first()
    if last and last.content_hash == h:
        return None
    return Card.objects.create(dataset=ds, version=(last.version + 1 if last else 1), short=short, full=full,
                               tokens_short=tokens(short), tokens_full=tokens(full), content_hash=h)


def compile_portal(portal, with_ids=False):
    changed, unchanged = [], 0
    for ds in Dataset.objects.filter(portal=portal).prefetch_related("fields", "edits"):
        if compile_dataset(ds):
            changed.append(ds.dataset_id)
        else:
            unchanged += 1
    out = {"compiled": len(changed), "unchanged": unchanged}
    if with_ids:
        out["changed"] = changed
    return out


def current(ds):
    return ds.cards.order_by("-version").first()


__all__ = ["compile_dataset", "compile_portal", "render", "current", "ContextEdit"]
