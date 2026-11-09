"""Explore API mock built from recorded responses of data.education.gouv.fr (09.11.2026)."""
import json
from pathlib import Path

import httpx

FIX = Path(__file__).resolve().parent / "fixtures"
CATALOG = json.loads((FIX / "catalog-education.json").read_text())
FACETS = json.loads((FIX / "facets-annuaire.json").read_text())
HEADERS = {"x-ratelimit-limit": "50000", "x-ratelimit-remaining": "49000"}


def api(catalog, seen=None, fail_on=None):
    def handler(request):
        path = request.url.path
        if seen is not None:
            seen.append(path)
        if fail_on and fail_on in path:
            return httpx.Response(500)
        if path.endswith("/catalog/exports/json"):
            return httpx.Response(200, json=catalog, headers=HEADERS)
        if path.endswith("/catalog/datasets"):
            return httpx.Response(200, json={"total_count": len(catalog), "results": catalog}, headers=HEADERS)
        if path.endswith("/facets"):
            return httpx.Response(200, json=FACETS if "annuaire" in path else {"facets": []}, headers=HEADERS)
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def load(portal, catalog=None):
    """Fill a portal from the fixtures (no network)."""
    from sources.explore import scan
    return scan(portal, full=True, transport=api(catalog or CATALOG))
