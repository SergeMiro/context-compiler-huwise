# Architecture baseline (audit, 11.11.2026)

State of the repository **before** the Huwise Architecture Explorer / Context Optimizer / AutoContext Lab work,
read from the code (branch `prod`, commit `91fa2ba`). Only what the code confirms is listed as working.

## What works (confirmed by code and tests)

| capability | where | confirmed by |
|---|---|---|
| Catalog import from Explore API v2.1 (full + incremental by `modified`, facet samples, PII fields skipped) | `sources/explore.py`, `sources/keys.py` | `catalog` tests with recorded fixtures (`tests/fixtures/`) |
| Single source of truth in MariaDB: `Portal`, `Dataset`, `Field`, `Transformation` | `catalog/models.py` | migrations, admin |
| Usage signal from the portal's published MCP log (`analyse-usage-mcp-et-agent-ia-copie`) | `sources/usage.py`, `signals` command | ES boost tests |
| Context cards: short ≤ 400 / full ≤ 1 500 tokens, deterministic, versioned (`Card.version`, content hash) | `ctx/compile.py`, `ctx/models.py` | `ctx/tests/test_compile.py` |
| Elasticsearch BM25 over cards, routed + filtered per portal, usage boost | `projections/es.py` | `projections/tests/test_es.py` |
| Neo4j shared keys and lineage, per-portal subgraph | `projections/graph.py` | `projections/tests/test_graph.py` |
| MCP server (streamable HTTP): `find_dataset`, `explain_dataset`, `query` | `mcpserver.py`, `tools/__init__.py` | `tools/tests/test_tools.py` |
| ODSQL whitelist validator (real field names only, `limit ≤ 100`, no comments, no extra params) | `tools/odsql.py` | `tools/tests/test_odsql.py` |
| Golden evals (30 questions, expected values computed from the API, no LLM judge), naked vs compiled | `evals/` | `evals/tests.py` |
| Improve loop: one LLM edit per failing dataset, keep if fixed and no control regression, else revert | `evals/improve.py`, `ctx.ContextEdit` | `evals/test_improve.py` |
| Celery + RabbitMQ cold path: scan → compile → project, one scan per portal (MariaDB `GET_LOCK`) | `ctx/tasks.py`, `ctx/locks.py` | `ctx/tests/test_tasks.py` |
| `llms.txt` + one markdown page per dataset | `ctx/export.py` | `ctx/tests/test_export.py` |
| Static French showcase + read-only JSON API (`/api/find|explain|query|raw|agent`) | `ctx/site.py`, `mcpserver.py` | `tests/test_api.py` |
| Public deployment: MCP + nginx behind traefik, 5 req/s per IP | `docker-compose.yml` (profile `public`) | running at context.smiro.dev |

Baseline test run before any change: **53 tests, OK** (`manage.py test`, local MariaDB/ES/Neo4j stand).

Recorded eval runs in the database at audit time (MariaDB `ctxc.evals_evalrun`): full 30-question naked/compiled
pairs #3/#4 (`nvidia/nemotron-3-ultra-550b-a55b:free`, 30 % → 80 %) and #10/#11 (`openai/gpt-5.4-mini`,
40 % → 90 %), plus 3-question smoke runs. These are internal experiments on a set seen during development.

## Not confirmed / not present at audit time

- No comparison against the real Huwise MCP server (it needs a portal API key; the "naked" baseline is our own
  generic toolset named after Huwise's tools).
- No train/validation/holdout split; the 30 golden questions were written and debugged together with the cards.
- No runtime evidence check: an agent's number was not compared to the API result outside the eval.
- No environment separation: the improve loop wrote cards in whatever database `.env` pointed to.
- No cache of query results, no routing, no recipes, no drift handling beyond card versions.

## Dependency map

```
Explore API v2.1 ──scan──> MariaDB (catalog) ──compile──> Card vN ──project──> ES `cards` / Neo4j
                                                   ^                               |
                                    ContextEdit (kept) <── improve <── eval <──────┤
MCP client ── find/explain/query ──> tools/ ── ES search · Card · Neo4j · validator ── Explore API (records)
```

## Commands that exist (audit)

`scan`, `signals`, `compile`, `project`, `export_llms`, `golden_refresh`, `eval`, `improve`, `mcp`, `bench`,
`build_site` — all `manage.py`; `scripts/bootstrap.sh`, `scripts/mcp_smoke.py`. Tests: `manage.py test`.
There was no `make`; the equivalents are listed in the README.

## Compatibility plan (followed)

- Keep Django, MariaDB, ES, Neo4j, Celery/RabbitMQ, MCP, export and every existing API route.
- New code goes in new packages (`optimizer/`, `lab/`) that call the existing hot path (`tools.query`) instead of
  replacing it; the MCP tools are unchanged.
- Migrations are additive only (`evals/0003`: `EvalCase.suite`, `EvalCase.split`, `EvalRun.mode` choice
  `optimized`). No data migration, no destructive change.
- Preprod gets its own database (`ctxc_preprod`, copied from `ctxc`) and ES alias (`cards_preprod`).
