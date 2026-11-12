import httpx
from django.test import SimpleTestCase, override_settings

import llm

CONF = dict(CTXC_LLM_BASE_URL="https://llm.example/v1", CTXC_LLM_API_KEY="k", CTXC_LLM_MODEL="some-model")
OK = {"choices": [{"message": {"content": None, "tool_calls": [
    {"id": "c1", "type": "function", "function": {"name": "find_dataset", "arguments": "{\"question\": \"x\"}"}}]}}],
      "usage": {"total_tokens": 42}}


class LlmTest(SimpleTestCase):
    def setUp(self):
        self._sleep, llm._sleep = llm._sleep, lambda s: None

    def tearDown(self):
        llm._sleep = self._sleep

    @override_settings(CTXC_LLM_BASE_URL="", CTXC_LLM_API_KEY="", CTXC_LLM_MODEL="", CTXC_LLM2_BASE_URL="", CTXC_LLM2_API_KEY="", CTXC_LLM2_MODEL="")
    def test_not_configured(self):
        with self.assertRaises(llm.LLMNotConfigured):
            llm.chat([{"role": "user", "content": "hi"}])

    @override_settings(**CONF)
    def test_tool_call_and_retry_on_429(self):
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(429) if len(seen) < 3 else httpx.Response(200, json=OK)
        out = llm.chat([{"role": "user", "content": "hi"}], tools=[{"type": "function"}],
                       transport=httpx.MockTransport(handler))
        self.assertEqual(len(seen), 3)
        self.assertEqual(seen[0].headers["authorization"], "Bearer k")
        self.assertEqual(out["message"]["tool_calls"][0]["function"]["name"], "find_dataset")
        self.assertEqual(out["tokens"], 42)

    @override_settings(**CONF)
    def test_gives_up_after_retries(self):
        with self.assertRaises(httpx.HTTPStatusError):
            llm.chat([], transport=httpx.MockTransport(lambda r: httpx.Response(503)))

    def test_fake(self):
        f = llm.FakeLLM([[("find_dataset", {"question": "écoles"})], "58 collèges"])
        a, b, c = f([]), f([]), f([])
        self.assertIn("écoles", a["message"]["tool_calls"][0]["function"]["arguments"])
        self.assertEqual((b["message"]["content"], c["message"]["content"]), ("58 collèges", "pas de données"))
