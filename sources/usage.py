"""Usage signals. data.education.gouv.fr publishes the log of what AI agents ask its Huwise MCP server
(dataset `analyse-usage-mcp-et-agent-ia-copie`: one row per call, Feb 2026 ->). We turn it into popularity per
dataset: the "usage context" that tells an agent which of five similar datasets people actually rely on."""
from django.db import transaction

from catalog.models import Dataset

from .explore import ExploreSource

USAGE_DATASET = "analyse-usage-mcp-et-agent-ia-copie"


def load_usage(portal, usage_dataset=USAGE_DATASET, transport=None):
    src = ExploreSource(portal.domain, transport=transport)
    rows = src.get(f"/catalog/datasets/{usage_dataset}/records", select="dataset_id, count(*) as n",
                   where="dataset_id is not null", group_by="dataset_id", limit=1000)["results"]
    counts = {r["dataset_id"]: r["n"] for r in rows}
    with transaction.atomic():
        Dataset.objects.filter(portal=portal).update(usage_count=0)
        known = Dataset.objects.filter(portal=portal, dataset_id__in=counts)
        for ds in known:
            ds.usage_count = counts[ds.dataset_id]
        Dataset.objects.bulk_update(known, ["usage_count"])
    return {"datasets_in_log": len(counts), "matched": len(known), "calls": sum(counts.values())}
