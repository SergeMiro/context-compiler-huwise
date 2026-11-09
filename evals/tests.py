import httpx
from django.test import TestCase

import tools
from catalog.models import Portal
from evals.golden import NO_DATA, load_golden, refresh
from evals.models import EvalCase
from tests.explore_mock import load


class GoldenTest(TestCase):
    def setUp(self):
        self.portal = Portal.objects.create(domain="data.education.gouv.fr")
        load(self.portal)
        self.seen, self._http = [], tools._http

        def handler(request):
            self.seen.append(dict(request.url.params))
            if "select" in request.url.params:
                return httpx.Response(200, json={"total_count": 1, "results": [{"v": 105.9, "libelle_academie": "Versailles"}]})
            return httpx.Response(200, json={"total_count": 58, "results": []})
        tools._http = httpx.Client(transport=httpx.MockTransport(handler))

    def tearDown(self):
        tools._http = self._http

    def test_load_is_idempotent_and_removes_stale(self):
        EvalCase.objects.create(portal=self.portal, slug="stale", question="?")
        n = load_golden(self.portal, "education")
        self.assertEqual(n, 30)
        self.assertEqual(load_golden(self.portal, "education"), 30)
        self.assertFalse(EvalCase.objects.filter(slug="stale").exists())

    def test_refresh_computes_answers_from_api(self):
        load_golden(self.portal, "education")
        EvalCase.objects.filter(portal=self.portal).exclude(
            slug__in=["colleges-publics-cote-dor", "academie-plus-ecoles", "no-data-medecins"]).delete()
        out = {slug: value for slug, value, _ in refresh(self.portal)}
        self.assertEqual(out, {"colleges-publics-cote-dor": 58, "academie-plus-ecoles": "Versailles",
                               "no-data-medecins": NO_DATA})
        self.assertEqual(self.seen[0]["limit"], "0")  # counts never download rows
