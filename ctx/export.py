"""Static, agent-readable export of a portal: llms.txt + one markdown page per dataset. Deterministic."""
from pathlib import Path

from catalog.models import Dataset
from ctx.compile import _first_sentences, current


def export_llms(portal, out_dir):
    out = Path(out_dir)
    (out / "datasets").mkdir(parents=True, exist_ok=True)
    lines = [f"# {portal.title or portal.domain}", "",
             f"> Datasets of {portal.domain} compiled for AI agents. Each page lists fields, value formats, "
             f"join keys and freshness. Query: https://{portal.domain}/api/explore/v2.1/catalog/datasets/<id>/records",
             "", "## Datasets", ""]
    written = 0
    for ds in Dataset.objects.filter(portal=portal).order_by("dataset_id").prefetch_related("cards"):
        card = current(ds)
        if card is None:
            continue
        (out / "datasets" / f"{ds.dataset_id}.md").write_text(card.full + "\n", encoding="utf-8")
        lines.append(f"- [{ds.title}](datasets/{ds.dataset_id}.md): {_first_sentences(ds.description, 160)}")
        written += 1
    (out / "llms.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return written
