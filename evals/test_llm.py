from unittest import mock

import httpx
from django.test import SimpleTestCase, override_settings

import llm

TWO = dict(CTXC_LLM_NAME="openrouter", CTXC_LLM_BASE_URL="https://or.example/v1", CTXC_LLM_API_KEY="k1",
           CTXC_LLM_MODEL="m1", CTXC_LLM2_NAME="nim", CTXC_LLM2_BASE_URL="https://nim.example/v1",
           CTXC_LLM2_API_KEY="k2", CTXC_LLM2_MODEL="m2")
OK = {"choices": [{"message": {"content": "23"}}], "usage": {"total_tokens": 5}}


@override_settings(**TWO)
class ProvidersTest(SimpleTestCase):
    def setUp(self):
        self.hits = []
        p = mock.patch.object(llm, "_sleep", lambda s: None)
        p.start()
        self.addCleanup(p.stop)

    def transport(self, down):
        def handler(req):
            self.hits.append((req.url.host, req.headers["authorization"]))
            return httpx.Response(429 if req.url.host in down else 200, json=OK)
        return httpx.MockTransport(handler)

    def test_picked_provider_answers_and_says_so(self):
        with llm.using("nim", fallback=True):
            r = llm.chat([], transport=self.transport(set()))
        self.assertEqual((r["provider"], r["model"]), ("nim", "m2"))
        self.assertEqual(self.hits, [("nim.example", "Bearer k2")])

    def test_429_moves_to_the_other_provider_at_once(self):
        with llm.using("openrouter", fallback=True):
            r = llm.chat([], transport=self.transport({"or.example"}))
        self.assertEqual(r["provider"], "nim")
        self.assertEqual([h for h, _ in self.hits], ["or.example", "nim.example"])

    def test_no_fallback_by_default_so_an_eval_measures_one_model(self):
        with self.assertRaises(httpx.HTTPStatusError):
            llm.chat([], transport=self.transport({"or.example"}))
        self.assertTrue(all(h == "or.example" for h, _ in self.hits))
        self.assertEqual(llm.model_name(), "m1")

    def test_public_list_has_no_keys(self):
        self.assertEqual(llm.public_providers(), [{"name": "openrouter", "model": "m1"}, {"name": "nim", "model": "m2"}])
