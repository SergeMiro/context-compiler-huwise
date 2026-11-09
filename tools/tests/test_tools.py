import asyncio
import json

import httpx
from django.test import TestCase, TransactionTestCase, override_settings

import tools
from catalog.models import Portal
from ctx.compile import compile_portal
from ctx.models import ToolCall
from mcpserver import resolve_portal
from projections import es, graph
from tests.explore_mock import load

SECRET_Q = "question-secrète-xyz"


def records_api(seen):
    def handler(request):
        seen.append(request)
        if request.url.params.get("where", "").startswith("departement"):
            return httpx.Response(400, json={"error_code": "ODSQLError", "message": "Unknown field: departement"})
        return httpx.Response(200, json={"total_count": 58, "results": []})
    return httpx.Client(transport=httpx.MockTransport(handler))


def setup_portals(case):
    es.drop_index()
    case.a = Portal.objects.create(domain="test-a.example")
    case.b = Portal.objects.create(domain="test-b.example")
    for p in (case.a, case.b):
        load(p)
        compile_portal(p)
    es.project_es(case.a)
    graph.project_graph(case.a)


@override_settings(ES_INDEX="test-cards")
class ToolsTest(TestCase):
    def setUp(self):
        setup_portals(self)
        self.seen, self._http = [], tools._http
        tools._http = records_api(self.seen)

    def tearDown(self):
        tools._http = self._http
        es.drop_index()
        graph.drop_portal("test-a.example")

    def test_find_explain_query(self):
        found = tools.find_dataset("test-a.example", "annuaire des établissements")
        self.assertIn("fr-en-annuaire-education", [r["dataset_id"] for r in found["results"]])
        card = tools.explain_dataset("test-a.example", "fr-en-annuaire-education")
        self.assertIn("code_departement", card["card"])
        self.assertTrue(card["joinable"])
        res = tools.query("test-a.example", "fr-en-annuaire-education",
                          {"select": "count(*) as n", "where": "code_departement='021'", "limit": 0}, api_key="k-123")
        self.assertEqual(res["total_count"], 58)
        self.assertEqual(self.seen[-1].headers["authorization"], "Apikey k-123")

    def test_errors_are_returned_to_the_agent(self):
        bad = tools.query("test-a.example", "fr-en-annuaire-education", {"where": "departement='21'"})
        self.assertIn("similar fields: code_departement", bad["error"])
        self.assertFalse(self.seen)  # rejected before spending the client's quota
        self.assertIn("unknown dataset", tools.explain_dataset("test-a.example", "fr-en-annuaire")["error"])
        self.assertIn("Unknown field", tools.naked_query("test-a.example", "fr-en-annuaire-education",
                                                         {"where": "departement='21'"})["error"])
        self.assertIn("unknown portal", tools.find_dataset("nope.example", "x")["error"])

    def test_tenant_isolation(self):
        self.assertEqual(tools.find_dataset("test-b.example", "annuaire")["results"], [])  # b not projected
        self.assertEqual(tools.explain_dataset("test-b.example", "fr-en-annuaire-education")["joinable"], [])

    def test_tool_calls_logged_without_content(self):
        tools.find_dataset("test-a.example", SECRET_Q)
        tools.query("test-a.example", "fr-en-annuaire-education", {"where": "nope=1"})
        rows = list(ToolCall.objects.values())
        self.assertEqual([(r["tool"], r["ok"], r["error_code"]) for r in rows],
                         [("find_dataset", True, ""), ("query", False, "odsql_rejected")])
        self.assertNotIn(SECRET_Q, json.dumps(rows, default=str))

    def test_naked_tools(self):
        self.assertTrue(tools.naked_search("test-a.example", "annuaire")["results"])
        got = tools.naked_get("test-a.example", "fr-en-annuaire-education")
        self.assertEqual(len(got["fields"]), 71)


class HeaderTest(TestCase):
    def test_header_beats_argument_and_key_passes_through(self):
        self.assertEqual(resolve_portal({"X-Domain": "a.example", "X-Apikey": "k"}, "b.example"), ("a.example", "k"))
        self.assertEqual(resolve_portal(None, "b.example"), ("b.example", None))


@override_settings(ES_INDEX="test-cards")
class McpInProcessTest(TransactionTestCase):
    def setUp(self):
        setup_portals(self)

    def tearDown(self):
        es.drop_index()
        graph.drop_portal("test-a.example")

    def test_list_and_call(self):
        from mcp import Client

        from mcpserver import server

        async def run():
            async with Client(server) as c:
                names = [t.name for t in (await c.list_tools()).tools]
                r = await c.call_tool("find_dataset", {"question": "annuaire", "portal": "test-a.example"})
                return names, r.structured_content or json.loads(r.content[0].text)
        names, found = asyncio.run(run())
        self.assertEqual(names, ["find_dataset", "explain_dataset", "query"])
        self.assertTrue(found["results"])
