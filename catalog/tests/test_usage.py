import httpx
from django.test import TestCase

from catalog.models import Dataset, Portal
from sources.usage import load_usage
from tests.explore_mock import CATALOG, load


class UsageTest(TestCase):
    def test_counts_matched_and_reset(self):
        portal = Portal.objects.create(domain="data.education.gouv.fr")
        load(portal)
        Dataset.objects.filter(portal=portal).update(usage_count=7)  # stale counts must be reset
        rows = [{"dataset_id": "fr-en-annuaire-education", "n": 3389}, {"dataset_id": "not-on-this-portal", "n": 5}]

        def handler(request):
            assert request.url.params["group_by"] == "dataset_id"
            return httpx.Response(200, json={"total_count": 2, "results": rows})
        stats = load_usage(portal, transport=httpx.MockTransport(handler))
        self.assertEqual(stats, {"datasets_in_log": 2, "matched": 1, "calls": 3394})
        self.assertEqual(Dataset.objects.get(dataset_id="fr-en-annuaire-education").usage_count, 3389)
        self.assertEqual(Dataset.objects.filter(usage_count=0).count(), len(CATALOG) - 1)
