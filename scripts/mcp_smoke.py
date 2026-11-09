"""Smoke test against a running MCP server: find -> explain -> count public collèges in Côte-d'Or (expect 58)."""
import asyncio
import json
import sys

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8796/mcp"


def data(result):
    return result.structured_content or json.loads(result.content[0].text)


async def main():
    async with httpx2.AsyncClient(headers={"X-Domain": "data.education.gouv.fr"}) as http, \
            Client(streamable_http_client(URL, http_client=http)) as c:
        print("tools:", [t.name for t in (await c.list_tools()).tools])
        found = data(await c.call_tool("find_dataset", {"question": "annuaire des établissements scolaires"}))
        print("find:", [r["dataset_id"] for r in found["results"]])
        card = data(await c.call_tool("explain_dataset", {"dataset_id": "fr-en-annuaire-education"}))
        print("explain:", card["card"].splitlines()[0], "| joinable:", len(card["joinable"]))
        res = data(await c.call_tool("query", {
            "dataset_id": "fr-en-annuaire-education", "select": "count(*) as n", "limit": 0,
            "where": "code_departement='021' and type_etablissement='Collège' and statut_public_prive='Public'"}))
        print("query:", res["total_count"])
        bad = data(await c.call_tool("query", {"dataset_id": "fr-en-annuaire-education", "where": "departement='21'"}))
        print("bad:", bad)


asyncio.run(main())
