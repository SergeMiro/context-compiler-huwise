"""Golden questions: written by hand, expected answers computed from the live API (never typed by hand)."""
import json
from pathlib import Path

from catalog.models import Dataset
from evals.models import EvalCase
from tools import ToolError, _records

GOLDEN = Path(__file__).resolve().parent / "golden"
NO_DATA = "no_data"


def load_golden(portal, name):
    rows = json.loads((GOLDEN / f"{name}.json").read_text())
    slugs = []
    for r in rows:
        EvalCase.objects.update_or_create(portal=portal, slug=r["slug"], defaults=dict(
            question=r["question"], expected_datasets=r["datasets"], reference_odsql=r.get("odsql", {}),
            answer_path=r.get("answer", "total_count"), tolerance=r.get("tolerance", 0.05), tags=r.get("tags", [])))
        slugs.append(r["slug"])
    EvalCase.objects.filter(portal=portal).exclude(slug__in=slugs).delete()
    return len(rows)


def reference_answer(portal, case):
    if not case.expected_datasets:
        return NO_DATA
    ds = Dataset.objects.get(portal=portal, dataset_id=case.expected_datasets[0])
    params = dict(case.reference_odsql)
    if case.answer_path == "total_count":
        params["limit"] = 0
        return _records(portal, ds.dataset_id, params, None)["total_count"]
    params.setdefault("limit", 1)
    res = _records(portal, ds.dataset_id, params, None)["results"]
    if not res:
        raise ToolError("empty", "reference query returned no rows")
    return res[0][case.answer_path.split(":", 1)[1]]


def refresh(portal):
    out = []
    for case in EvalCase.objects.filter(portal=portal).order_by("id"):
        try:
            value = reference_answer(portal, case)
        except ToolError as e:
            out.append((case.slug, None, str(e)))
            continue
        case.expected_value = value
        case.save(update_fields=["expected_value"])
        suspect = "SUSPECT: empty/zero" if value in (0, None, "") else ""
        out.append((case.slug, value, suspect))
    return out
