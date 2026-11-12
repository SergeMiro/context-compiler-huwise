from django.test import TestCase

from catalog.models import Portal
from mcpserver import DEMO_PORTAL, api_call


class ShowcaseApiTest(TestCase):
    def setUp(self):
        Portal.objects.create(domain=DEMO_PORTAL)

    def test_required_args(self):
        self.assertEqual(api_call("find", {})[0], 400)
        self.assertEqual(api_call("explain", {"id": "  "})[0], 400)
        self.assertEqual(api_call("query", {"id": "x", "limit": "abc"})[0], 400)

    def test_unknown_dataset_is_a_tool_error_not_a_crash(self):
        status, body = api_call("explain", {"id": "nope"})
        self.assertEqual(status, 200)
        self.assertIn("unknown dataset", body["error"])
        status, body = api_call("query", {"id": "nope", "limit": "500"})
        self.assertIn("unknown dataset", body["error"])


class LiveAgentTest(TestCase):
    def setUp(self):
        from evals.models import EvalCase
        portal = Portal.objects.create(domain=DEMO_PORTAL)
        EvalCase.objects.create(portal=portal, slug="q1", question="Combien ?", expected_datasets=["d"],
                                expected_value=58)

    def test_bad_args(self):
        from mcpserver import live_agent
        self.assertEqual(live_agent({"mode": "x", "slug": "q1"})[0], 400)
        self.assertEqual(live_agent({"mode": "naked", "slug": "nope"})[0], 404)

    def test_runs_scores_caches_and_caps(self):
        from unittest import mock

        import mcpserver
        from llm import FakeLLM
        mcpserver._live.update(day=None, runs=0, cache={})
        fake = FakeLLM(["Il y a 58 collèges."])
        with mock.patch("evals.agent.llm_mod.chat", fake), mock.patch.object(mcpserver, "LIVE_RUNS_PER_DAY", 1):
            status, body = mcpserver.live_agent({"mode": "compiled", "slug": "q1"})
            self.assertEqual((status, body["answer_ok"], body["trace"]), (200, True, []))
            self.assertIn("cached_s", mcpserver.live_agent({"mode": "compiled", "slug": "q1"})[1])  # no 2nd model call
            self.assertEqual(len(fake.calls), 1)
            self.assertEqual(mcpserver.live_agent({"mode": "naked", "slug": "q1"})[0], 429)  # cap of 1 reached


class CondenseTest(TestCase):
    def test_pairs_calls_with_results(self):
        from evals.runner import condense
        t = [{"role": "system", "content": "s"}, {"role": "user", "content": "q"},
             {"role": "assistant", "content": None, "tool_calls": [
                 {"id": "a", "function": {"name": "query", "arguments": '{"where": "x=1"}'}}]},
             {"role": "tool", "tool_call_id": "a", "content": '{"error": "bad"}'},
             {"role": "assistant", "content": "fin"}]
        self.assertEqual(condense(t), [{"tool": "query", "args": {"where": "x=1"}, "ok": False,
                                        "result": '{"error": "bad"}'}])


class DemoRunTest(TestCase):
    def test_live_runs_are_checked_and_capped(self):
        from unittest import mock

        import mcpserver
        from mcpserver import demo_run
        self.assertEqual(demo_run({"scenario": "nope"})[0], 404)
        self.assertEqual(demo_run({"scenario": "drift"})[0], 404)  # simulated: never live
        self.assertEqual(demo_run({"scenario": "dijon", "mode": "admin"})[0], 400)
        self.assertEqual(demo_run({"scenario": "dijon", "mode": "naked", "provider": "nope"})[0], 400)
        with mock.patch.dict("os.environ", {"HUWISE_API_KEY": ""}):
            self.assertEqual(demo_run({"scenario": "dijon", "mode": "huwise"})[0], 503)  # no key: recording only
        with mock.patch.object(mcpserver, "LIVE_RUNS_PER_DAY", 0):  # a model run counts against the daily cap
            self.assertEqual(demo_run({"scenario": "trap-dataset", "mode": "compiled"})[0], 429)
