# Context Compiler — Huwise

Compiles a Huwise / Opendatasoft data portal (Explore API v2.1) into **context for AI agents**, and measures
whether it helps.

- one short, token-budgeted **card per dataset**: what it is, freshness, licence, join keys *with their real value
  format*, fields, query hints;
- **Elasticsearch** search over cards, boosted by **usage signals** (what agents actually used);
- **Neo4j** graph of datasets that can be joined (shared keys) and lineage;
- an **MCP server** with three tools — `find_dataset`, `explain_dataset`, `query` (ODSQL validated against the
  real schema before it costs the client any quota);
- an **eval harness**: the same agent answers 30 golden questions with generic catalog tools (`naked`) and with
  the compiled cards (`compiled`), scored without an LLM judge;
- an **improve loop**: an LLM proposes one card edit per failing dataset; the edit is kept only if failures get
  fixed and no passing question breaks. A human can review the diff in Django admin.

**Live:** showcase <https://context.smiro.dev/> · read-only MCP `https://context.smiro.dev/mcp`
(`claude mcp add --transport http context https://context.smiro.dev/mcp --header "X-Domain: data.education.gouv.fr"`).

Development portal: `data.education.gouv.fr` (French Ministry of Education, runs on Huwise).
Stack — the same as Huwise: Django + DRF, MariaDB, Celery + RabbitMQ, Elasticsearch, Neo4j, MCP Python SDK.

## Why

A portal already exposes an API per dataset, and a generic MCP server gives agents access to all of it. What an agent
lacks is **context**: which of five similar datasets is the right one, which field means what, how values are
written. On this portal alone, writing 30 reference queries by hand failed 11 times on exactly that:

| trap | example |
|---|---|
| one department, three formats | Côte-d'Or is `'021'` in the directory, `'21'` in IPS datasets, `"COTE D'OR"` as a label |
| years stored as dates | `session='2025'` → API type error; `year(session)=2025` works |
| numbers stored as text | `avg(ips)` fails on IPS écoles; `order_by ips_etab desc` sorts as strings |
| case differs | `academie='DIJON'` vs `libelle_academie='Dijon'` |

The portal also publishes the log of its own MCP server (`analyse-usage-mcp-et-agent-ia-copie`, 39 675 agent calls,
Feb–Nov 2026). It is used here as the usage signal: the directory `fr-en-annuaire-education` is the most used dataset
(3 389 calls), yet plain BM25 does not put it in the top 5 for "combien d'écoles en France". With the signal it is #1.

## Result

Same model (`nemotron-3-ultra-550b`, free on OpenRouter), same prompt, 30 golden questions, scored without an LLM judge:

| | naked (generic catalog tools) | compiled (cards) |
|---|---|---|
| correct answer | 30 % | **80 %** |
| right dataset | 53 % | 83 % |
| valid query on the 1st try | 57 % | 86 % |
| tokens | 414 k | 424 k |

What still fails and why: [`NOTES.md`](NOTES.md#t17--first-real-eval-10112026).

## Architecture

```
COLD PATH (commands / Celery; the only place an LLM is ever called)
  Explore API --scan--> Portal / Dataset / Field   (MariaDB = single source of truth)
                          | compile (deterministic)
                          v
                        Card v1..vN  <-- kept ContextEdit
             +------------+-------------+
             v            v             v
        ES `cards`     Neo4j          llms.txt + datasets/<id>.md
  eval:    EvalCase -> agent -> EvalRun / EvalResult
  improve: failures -> LLM proposes edit -> compile -> eval -> kept | reverted

HOT PATH (MCP, no LLM, no writes except the ToolCall log)
  find_dataset(question) -> ES (filter + routing by portal) + usage boost -> short cards
  explain_dataset(id)    -> full card + joinable datasets + lineage (Neo4j)
  query(id, odsql)       -> validator -> Explore API (client key passed through, limit <= 100)
```

Measured on the dev portal (`manage.py bench`, in process): `find_dataset` p95 13 ms, `explain_dataset` p95 23 ms.
Full scan of 314 datasets / 6 976 fields: 1 catalog request + 182 facet requests, ~36 s; incremental scan with no
changes: 1 request, 0.2 s.

## Run locally

Needs Docker, Python 3.12, `libmariadb-dev` and `pkg-config` (for `mysqlclient`). About 3 GB RAM for the services.

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env
scripts/bootstrap.sh                       # services, schema, scan, signals, cards, ES, Neo4j, golden answers
.venv/bin/python manage.py test            # 45 tests (use the local ES / Neo4j / MariaDB)
.venv/bin/python manage.py mcp             # MCP server: http://127.0.0.1:8796/mcp (header X-Domain)
.venv/bin/python scripts/mcp_smoke.py      # find -> explain -> count public collèges in Côte-d'Or = 58
```

LLM features (eval, improve) need any OpenAI-compatible endpoint in `.env`: `CTXC_LLM_BASE_URL`,
`CTXC_LLM_API_KEY`, `CTXC_LLM_MODEL`. No provider is hard-coded.

```bash
.venv/bin/python manage.py eval data.education.gouv.fr --mode both     # table naked vs compiled
.venv/bin/python manage.py improve data.education.gouv.fr --mode propose
.venv/bin/python manage.py runserver 127.0.0.1:8797                    # /admin: cards, edit diffs, eval runs
.venv/bin/celery -A context worker -B                                  # hourly scan -> compile -> project
```

## Commands

| command | does |
|---|---|
| `scan <domain> [--full]` | catalog → datasets/fields; incremental by `modified`; facet values as samples (never for PII fields) |
| `signals <domain>` | usage per dataset from the portal's MCP usage log |
| `compile <domain>` | cards (short ≤ 400, full ≤ 1 500 tokens), new version only if the text changed |
| `project <domain> [--rebuild-index]` | ES + Neo4j for this portal (other portals untouched) |
| `export_llms <domain> <dir>` | `llms.txt` + one markdown page per dataset |
| `golden_refresh <domain>` | load `evals/golden/<set>.json`, compute expected answers from the API |
| `eval <domain> --mode naked\|compiled\|both` | run the golden set, print the comparison table |
| `improve <domain> --mode propose\|auto` | propose / test / keep or revert card edits |
| `mcp [--host]`, `bench <domain>` | MCP server; latency p50/p95 |
| `build_site <domain> <dir>` | static showcase: `index.html` (traps, eval table, a card, an edit) + `llms.txt` + pages |

Public deployment (this server): `docker compose --profile public up -d --build mcp site` — the MCP container and an
nginx serving `site/`, behind the host's traefik (`infra_web`, Let's Encrypt, 5 req/s per IP). Django admin is not
exposed.

## Scale: 3 000–5 000 portals

| what | size | how |
|---|---|---|
| datasets / fields | ~750 000 / ~15 M | MariaDB, indexes (portal, modified), (dataset, name) |
| scanning | 1 request per portal for a full scan, 1–3 per hour incremental | Celery on RabbitMQ, portals spread over the hour, one scan per portal (MariaDB `GET_LOCK`), ≤ 5 % of each portal's daily API quota |
| search | ~750 000 cards | one ES index, `routing` + `filter` by portal |
| graph | linear in key fields | `(:Dataset)-[:HAS_KEY]->(:Key)` instead of an edge per pair (79 edges instead of 3 081 for `uai`) |
| hot path | 1 ES query + cache | stateless MCP server, scale horizontally |
| LLM | offline only | daily budget per portal |

## Security

- Tenant isolation in every query (MariaDB, ES `routing` + `filter`, Neo4j `MATCH {portal}`), with tests.
- The client's API key (`X-Apikey`) is only passed through to the Explore API: never stored or logged.
- ODSQL whitelist: only real field names, `limit ≤ 100`, no comments or extra parameters.
- PII-like fields (`mail`, `telephone`, `adresse`, `nom`…) get no sample values and never reach cards or the LLM.
- Rate limit per portal on the MCP server and per IP at the proxy; admin binds to 127.0.0.1, only MCP and the
  static site are public.
- `ToolCall` logs tool, latency and error code — never the question or the query.

## Not done (on purpose)

No LLM on the hot path · no vector search until the eval shows recall is the bottleneck · no LLM judge · no
LangChain/LangGraph (the agent loop is ~100 lines) · no glossary model yet (synonyms are card edits).
Decisions and what did not work: [`NOTES.md`](NOTES.md). Build plan (Russian): [`docs/PLAN.md`](docs/PLAN.md).

## Licence

MIT, see [`LICENSE`](LICENSE).

## Branches

`feat/*` → `dev` (development) → `preprod` (verified) → `prod` (stable, default).
