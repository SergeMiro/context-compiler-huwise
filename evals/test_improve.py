import json

import httpx
from django.test import TestCase, override_settings

import tools
from catalog.models import Portal
from ctx.compile import compile_portal, current
from ctx.models import ContextEdit
from evals.golden import load_golden
from evals.improve import improve
from evals.models import EvalCase
from evals.runner import run_eval
from llm import FakeLLM
from projections import es
from tests.explore_mock import load

CASE = "colleges-publics-cote-dor"
NOTE = "code_departement has 3 digits: Côte-d'Or = '021'"


def agent(answer_for):
    """Fake agent: one query, then an answer chosen from the system state (does the card have the note?)."""
    class Agent:

        def __call__(self, messages, tools=None, temperature=0):
            q = next(m["content"] for m in messages if m["role"] == "user")
            if len([m for m in messages if m["role"] == "assistant"]) == 0:
                return FakeLLM([[("query", {"dataset_id": "fr-en-annuaire-education", "limit": 0})]])([])
            return FakeLLM([answer_for(q)])([])
    return Agent()


@override_settings(ES_INDEX="test-cards")
@override_settings(CTXC_ENV="preprod")
class ImproveTest(TestCase):
    def setUp(self):
        es.drop_index()
        self.portal = Portal.objects.create(domain="data.education.gouv.fr")
        load(self.portal)
        compile_portal(self.portal)
        load_golden(self.portal, "education")
        EvalCase.objects.filter(portal=self.portal).exclude(
            slug__in=[CASE, "ecoles-france", "etablissements-ulis"]).delete()
        for slug, v in [(CASE, 58), ("ecoles-france", 48336), ("etablissements-ulis", 10426)]:
            EvalCase.objects.filter(slug=slug).update(expected_value=v)
        self._http = tools._http
        tools._http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"total_count": 1, "results": []})))
        self.annuaire = self.portal.datasets.get(dataset_id="fr-en-annuaire-education")

    def tearDown(self):
        tools._http = self._http
        es.drop_index()

    def _has_note(self):
        return NOTE in current(self.annuaire).full

    def _answers(self, regress):
        def answer(q):
            if "collèges publics" in q:
                return "Il y a 58 collèges." if self._has_note() else "Il y a 0 collège."
            if "écoles" in q:
                return "Il y a 1 école." if (regress and self._has_note()) else "Il y a 48 336 écoles."
            return "Il y a 10 426 établissements."
        return answer

    def _run(self, regress):
        base = run_eval(self.portal, "compiled", chat=agent(self._answers(regress)), model="fake")
        self.assertEqual(base.metrics["per_case"][CASE]["answer_ok"], False)
        proposer = FakeLLM([json.dumps({"kind": "note", "after": NOTE, "rationale": "agent used '21'"})])
        return improve(self.portal, mode="auto", run=base, proposer=proposer, agent=agent(self._answers(regress)))

    def test_edit_that_fixes_is_kept(self):
        s = self._run(regress=False)
        self.assertEqual((s["proposed"], s["kept"], s["correct_before"], s["correct_after"]), (1, 1, 2, 3))
        e = ContextEdit.objects.get()
        self.assertEqual(e.eval_after["fixed"], [CASE])
        self.assertTrue(self._has_note())

    def test_edit_that_breaks_a_passing_case_is_reverted(self):
        s = self._run(regress=True)
        self.assertEqual((s["kept"], s["reverted"]), (0, 1))
        self.assertEqual(ContextEdit.objects.get().eval_after["broken"], ["ecoles-france"])
        self.assertFalse(self._has_note())  # card rolled back

    def test_budget_and_invalid_json(self):
        self.portal.llm_budget_per_day = 1
        self.portal.save()
        base = run_eval(self.portal, "compiled", chat=agent(self._answers(False)), model="fake")
        s = improve(self.portal, mode="propose", run=base, proposer=FakeLLM(["not json"]))
        self.assertEqual(s["proposed"], 0)
        self.assertEqual(ContextEdit.objects.get().status, "rejected")
        s = improve(self.portal, mode="propose", run=base, proposer=FakeLLM(["{}"]))
        self.assertEqual(ContextEdit.objects.count(), 1)  # budget of 1 LLM call/day already spent


    def test_lab_cycle_keeps_reverts_logs_and_respects_budget(self):
        import tempfile
        from pathlib import Path

        from lab import log
        from lab.cycle import run_cycle
        with tempfile.TemporaryDirectory() as d, override_settings(CTXC_LAB_LOG=str(Path(d) / "lab.jsonl")):
            base = run_eval(self.portal, "compiled", chat=agent(self._answers(False)), model="fake")
            proposer = FakeLLM([json.dumps({"kind": "note", "after": NOTE, "rationale": "agent used '21'"})])
            rows = run_cycle(self.portal, base, chat=proposer, agent=agent(self._answers(False)))
            steps = [r["entry"]["step"] for r in rows]
            self.assertEqual(steps, ["collect+diagnose", "experiment", "done"])
            self.assertEqual(rows[0]["entry"]["failures"], {CASE: "hallucinated_value"})  # said 0, the API returned 1
            self.assertEqual(rows[1]["entry"]["decision"], "kept")
            self.assertEqual(log.verify(), (True, None))
            # a candidate that breaks a control case is reverted and the card goes back
            ContextEdit.objects.all().delete()
            from ctx.compile import compile_dataset
            compile_dataset(self.annuaire)
            proposer = FakeLLM([json.dumps({"kind": "note", "after": NOTE, "rationale": "x"})])
            rows = run_cycle(self.portal, base, chat=proposer, agent=agent(self._answers(True)))
            self.assertEqual(rows[1]["entry"]["decision"], "reverted")
            self.assertFalse(self._has_note())
            # budget: one model call allowed, the proposer uses it, the eval cannot start
            ContextEdit.objects.all().delete()
            compile_dataset(self.annuaire)
            proposer = FakeLLM([json.dumps({"kind": "note", "after": NOTE, "rationale": "x"})])
            rows = run_cycle(self.portal, base, chat=proposer, agent=agent(self._answers(False)), max_calls=1)
            self.assertEqual(rows[1]["entry"]["decision"], "stopped")
            self.assertEqual(log.verify(), (True, None))
