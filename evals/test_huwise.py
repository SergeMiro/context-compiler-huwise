import json
from unittest import mock

import httpx
from django.test import SimpleTestCase

from evals import huwise_mcp

TOOLS = {"tools": [{"name": "search_asset_records", "description": "Query records.",
                    "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}, "slug": {"type": "string"}},
                                    "required": ["url", "slug"]}}]}


class HuwiseMcpTest(SimpleTestCase):
    def setUp(self):
        self.sent = []

        def handler(req):
            body = json.loads(req.content)
            self.sent.append((dict(req.headers), body))
            if body["method"] == "tools/list":
                return httpx.Response(200, text="event: message\ndata: " + json.dumps({"result": TOOLS}) + "\n\n")
            if body["params"]["arguments"].get("slug") == "bad":
                return httpx.Response(200, json={"result": {"content": [{"type": "text", "text": "no such asset"}],
                                                            "isError": True}})
            return httpx.Response(200, json={"result": {"content": [{"type": "text", "text": "{}"}],
                                                        "structuredContent": {"result": {"total_count": 23}}}})
        self.p = [mock.patch.object(huwise_mcp, "_http", httpx.Client(transport=httpx.MockTransport(handler))),
                  mock.patch.dict("os.environ", {"HUWISE_API_KEY": "k"})]
        for p in self.p:
            p.start()
        huwise_mcp.specs.cache_clear()

    def tearDown(self):
        for p in self.p:
            p.stop()

    def test_toolset_hides_url_and_calls_the_server_with_key_and_portal(self):
        ts = huwise_mcp.toolset("data.example.org")
        spec, fn = ts["search_asset_records"]
        self.assertNotIn("url", spec["function"]["parameters"]["properties"])
        self.assertEqual(spec["function"]["parameters"]["required"], ["slug"])
        self.assertEqual(fn("data.example.org", {"slug": "x"}), {"total_count": 23})
        headers, body = self.sent[-1]
        self.assertEqual(body["params"]["arguments"]["url"], "https://data.example.org")
        self.assertEqual((headers["x-apikey"], headers["x-domain"]), ("k", "https://data.example.org"))
        self.assertEqual(fn("data.example.org", {"slug": "bad"}), {"error": "no such asset"})

    def test_no_key_is_an_explicit_error(self):
        with mock.patch.dict("os.environ", {"HUWISE_API_KEY": ""}):
            with self.assertRaises(RuntimeError):
                huwise_mcp.call("data.example.org", "search_asset_records", {"slug": "x"})
