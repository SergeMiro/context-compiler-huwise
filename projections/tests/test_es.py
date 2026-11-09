from django.test import TestCase, override_settings

from catalog.models import Portal
from ctx.compile import compile_portal
from projections import es
from tests.explore_mock import CATALOG, load


@override_settings(ES_INDEX="test-cards")
class EsTest(TestCase):
    def setUp(self):
        es.drop_index()
        self.a = Portal.objects.create(domain="a.example")
        self.b = Portal.objects.create(domain="b.example")
        for p in (self.a, self.b):
            load(p)
            compile_portal(p)

    def tearDown(self):
        es.drop_index()

    def test_search_finds_dataset_and_isolates_tenants(self):
        self.assertEqual(es.project_es(self.a), len(CATALOG))
        hits = es.search("a.example", "collèges publics Côte-d'Or", k=3)
        self.assertIn("fr-en-annuaire-education", [h["dataset_id"] for h in hits])
        self.assertEqual(es.search("b.example", "collèges"), [])  # b not projected yet: sees nothing of a
        es.project_es(self.b)
        self.assertEqual(es.project_es(self.a), len(CATALOG))  # re-projecting a keeps b
        self.assertTrue(es.search("b.example", "collèges"))
        self.assertTrue(all(h["dataset_id"] for h in es.search("a.example", "college")))  # accent folding

    def test_rebuild_keeps_alias(self):
        es.project_es(self.a)
        ok, new = es.rebuild_index([self.a, self.b])
        self.assertEqual(ok, 2 * len(CATALOG))
        self.assertEqual(list(es.client().indices.get_alias(name="test-cards")), [new])
