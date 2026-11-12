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


class RunnerScoringTest(TestCase):
    def test_numbers_fr(self):
        from evals.runner import numbers
        self.assertEqual(numbers("Il y a 48 336 écoles, soit 1 234,5 par académie et 58."), [48336.0, 1234.5, 58.0])
        self.assertEqual(numbers("IPS moyen : 105,88"), [105.88])

    def test_answer_ok(self):
        from evals.runner import answer_ok
        c = EvalCase(question="Combien de collèges publics en 2025 en Côte-d'Or (21) ?", expected_value=58, tolerance=0.05)
        self.assertTrue(answer_ok(c, "Il y a 58 collèges publics."))
        self.assertFalse(answer_ok(c, "En 2025, dans le 21, je ne sais pas."))  # numbers from the question ignored
        self.assertTrue(answer_ok(EvalCase(question="?", expected_value=105.88, tolerance=0.05), "IPS ≈ 106"))
        self.assertTrue(answer_ok(EvalCase(question="?", expected_value="Versailles"), "L'académie de VERSAILLES."))
        self.assertTrue(answer_ok(EvalCase(question="?", expected_value=NO_DATA), "Pas de données sur ce portail."))


class AgentLoopTest(TestCase):
    def setUp(self):
        self.portal = Portal.objects.create(domain="data.education.gouv.fr")
        load(self.portal)
        load_golden(self.portal, "education")
        self._http = tools._http
        tools._http = httpx.Client(transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"total_count": 58, "results": []})))

    def tearDown(self):
        tools._http = self._http

    def test_stops_after_max_steps(self):
        from evals.agent import MAX_STEPS, run_agent
        from llm import FakeLLM
        fake = FakeLLM([[("query", {"dataset_id": "fr-en-annuaire-education", "where": "nope=1"})]] * 10)
        res = run_agent("data.education.gouv.fr", "?", "compiled", chat=fake)
        self.assertEqual((res["steps"], res["answer"]), (MAX_STEPS, ""))
        self.assertEqual(res["queries"][0], {"dataset_id": "fr-en-annuaire-education", "ok": False,
                                             "params": {"where": "nope=1"}, "result": None})

    def test_last_step_has_no_tools(self):
        from evals.agent import MAX_STEPS, run_agent
        from llm import FakeLLM
        fake, seen = FakeLLM([[("query", {"dataset_id": "fr-en-annuaire-education", "where": "nope=1"})]] * 10), []

        def chat(messages, tools=None):
            seen.append(tools)
            return fake(messages, tools)
        run_agent("data.education.gouv.fr", "?", "compiled", chat=chat)
        self.assertEqual(len(seen), MAX_STEPS)
        self.assertTrue(all(seen[:-1]))
        self.assertIsNone(seen[-1])

    def test_full_run_both_modes_on_fake(self):
        from evals.runner import run_eval, table
        from llm import FakeLLM

        def fake_factory():
            script = []
            for _ in range(30):
                script += [[("query", {"dataset_id": "fr-en-annuaire-education", "select": "count(*) as n", "limit": 0})],
                           "Il y a 58 établissements."]
            return FakeLLM(script)
        EvalCase.objects.filter(slug__startswith="no-data").update(expected_value=NO_DATA)
        compiled = run_eval(self.portal, "compiled", chat=fake_factory(), model="fake")
        naked = run_eval(self.portal, "naked", chat=FakeLLM([]), model="fake")  # always "pas de données"
        self.assertEqual(compiled.results.count(), 30)
        self.assertEqual(naked.metrics["answer_ok"], round(100 * 2 / 30, 1))  # only the 2 no-data cases
        self.assertIn("| correct answer % |", table([naked, compiled]))
