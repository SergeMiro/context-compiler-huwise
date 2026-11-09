import time

from django.test import TestCase

from catalog.models import Dataset, Portal, Transformation
from projections import graph
from tests.explore_mock import load


class GraphTest(TestCase):
    def setUp(self):
        self.a = Portal.objects.create(domain="test-a.example")
        self.b = Portal.objects.create(domain="test-b.example")
        load(self.a)
        load(self.b)

    def tearDown(self):
        for p in (self.a, self.b):
            graph.drop_portal(p.domain)

    def _count(self, p):
        return graph._run("""MATCH (d:Dataset {portal: $p}) OPTIONAL MATCH (d)-[r]->()
                             RETURN count(DISTINCT d) AS n, count(r) AS r""", p=p)[0]

    def test_joinable_by_shared_keys_and_tenant_isolation(self):
        graph.project_graph(self.a)
        t = time.monotonic()
        rows = graph.joinable("test-a.example", "fr-en-annuaire-education")
        self.assertLess(time.monotonic() - t, 0.5)
        self.assertTrue(rows)
        self.assertTrue(all(r["on"] for r in rows))
        self.assertEqual(graph.joinable("test-b.example", "fr-en-annuaire-education"), [])  # b not projected

    def test_idempotent_and_lineage(self):
        x, y = Dataset.objects.filter(portal=self.a)[:2]
        Transformation.objects.create(source=x, target=y, kind="aggregate")
        graph.project_graph(self.a)
        first = self._count("test-a.example")
        graph.project_graph(self.a)
        self.assertEqual(self._count("test-a.example"), first)
        self.assertEqual(graph.lineage("test-a.example", y.dataset_id)["upstream"], [{"dataset_id": x.dataset_id, "depth": 1}])
        self.assertEqual(graph.lineage("test-a.example", x.dataset_id)["downstream"], [{"dataset_id": y.dataset_id, "depth": 1}])
        x.delete()
        graph.project_graph(self.a)
        self.assertEqual(self._count("test-a.example")["n"], first["n"] - 1)
