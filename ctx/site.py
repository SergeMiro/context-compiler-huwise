"""Static showcase of a portal: index.html (what, traps, eval table, one card, one edit) + llms.txt + datasets/*.md.
Everything comes from the database; no secrets, no JavaScript."""
from pathlib import Path

from django.template.loader import render_to_string

from catalog.models import Dataset, Field
from ctx.compile import current
from ctx.export import export_llms
from ctx.models import Card, ContextEdit
from evals.models import EvalRun
from evals.runner import table

SHOWCASE_DATASET = "fr-en-annuaire-education"
METRICS = [("answer_ok", "correct answer, %"), ("dataset_ok", "right dataset, %"),
           ("odsql_first_try", "valid query on the 1st try, %"), ("steps_avg", "steps per question"),
           ("ms_median", "median time, ms"), ("tokens", "tokens, total")]


def latest_pair(portal):
    """Latest `eval --mode both` over the full golden set: a compiled run right after a naked run of the same model
    (same cards, same harness), or None."""
    full = portal.eval_cases.count()
    for c in EvalRun.objects.filter(portal=portal, mode="compiled", finished_at__isnull=False).order_by("-id"):
        n = EvalRun.objects.filter(portal=portal, id=c.id - 1, mode="naked", model=c.model).first()
        if n and n.metrics.get("n") == c.metrics.get("n") == full:
            return n, c
    return None


def build_site(portal, out_dir):
    out = Path(out_dir)
    pages = export_llms(portal, out)
    pair = latest_pair(portal)
    rows = [(label, pair[0].metrics.get(k), pair[1].metrics.get(k)) for k, label in METRICS] if pair else []
    ds = Dataset.objects.filter(portal=portal, dataset_id=SHOWCASE_DATASET).first()
    card = current(ds) if ds else None
    edit = (ContextEdit.objects.filter(dataset__portal=portal, status="kept").order_by("-decided_at").first()
            or ContextEdit.objects.filter(dataset__portal=portal).order_by("-created_at").first())
    ctx = {
        "domain": portal.domain, "pages": pages,
        "datasets": Dataset.objects.filter(portal=portal).count(),
        "fields": Field.objects.filter(dataset__portal=portal).count(),
        "cards": Card.objects.filter(dataset__portal=portal).values("dataset").distinct().count(),
        "top": Dataset.objects.filter(portal=portal, usage_count__gt=0).order_by("-usage_count")[:5],
        "pair": pair, "rows": rows, "table": table(list(pair)) if pair else "",
        "card": card, "edit": edit,
    }
    (out / "index.html").write_text(render_to_string("ctx/site.html", ctx), encoding="utf-8")
    return pages
