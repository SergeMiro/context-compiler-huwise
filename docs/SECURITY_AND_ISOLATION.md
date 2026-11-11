# Security and isolation

## Environments

| | production | preprod |
|---|---|---|
| hostname | context.smiro.dev | context-preprod.smiro.dev |
| Compose project | `context-compiler-huwise` (profile `public`) | `ctxc-preprod` (`docker-compose.preprod.yml`) |
| image | built from `prod` | `ctxc-preprod-mcp`, built from the feature branch |
| MariaDB database / user | `ctxc` / `ctxc` | `ctxc_preprod` / `ctxc_preprod` (grants on its own database only) |
| Elasticsearch alias | `cards` | `cards_preprod` |
| Neo4j | read + write (projection) | **read-only**: `project_graph` returns "skipped" when `CTXC_ENV=preprod` |
| AutoContext Lab | refused (`lab.cycle.guard`) | allowed |
| `apply_edit` (writes a candidate card) | refused | allowed |
| model calls from the public page | `/api/agent`, 15/day | `/api/agent`, 5/day; `/api/demo/run` never calls a model |
| secrets | `.env` | `.env.preprod` (mode 600, git-ignored, docker-ignored) |

Shared on purpose (RAM on one VPS): the MariaDB, Elasticsearch and Neo4j **servers** and the RabbitMQ broker of the
local stand. Separation is by database, ES alias and environment guard. A dedicated server set per environment is
the next step if the project leaves a single VPS.

## Data access

- Only public open data of data.education.gouv.fr via the Explore API (GET). Nothing is ever written to the portal.
- The client `X-Apikey` is passed through to the Explore API, never stored, never logged, never part of a cache key
  (the cache uses an HMAC of it as "permission scope"; anonymous calls share the `public` scope).
- PII-like fields get no sample values and never reach cards, prompts or logs.
- ODSQL validator in front of every query: real field names only, `limit ≤ 100`, no comments, no extra parameters
  (unit + seeded property tests). An unknown field is refused before any API call.

## What the optimizer and the lab can touch

- The optimizer (hot path) writes nothing except the existing `ToolCall` log (tool, ms, ok, error code).
- The lab may create `ContextEdit` rows and new `Card` versions **in preprod**, and re-index them in
  `cards_preprod`. It cannot edit golden files, expected values, the evaluator, the validator, the evidence check,
  the policy or the log (code paths not exposed to it; the proposer only returns text for an edit of an allowed
  kind, and `static_check` rejects anything else).
- Holdout questions and their transcripts never reach the proposer.
- The log is append-only with a sha256 chain: editing or deleting a past line is detected by `lab log`.

## Budgets and limits

- Lab: `max_proposals`, `max_llm_calls`, `max_seconds` per cycle (`lab/policy.json`); one cycle at a time (CLI).
- MCP: 10 calls/s per portal in process; traefik 5 req/s per IP (burst 20) on both hostnames.
- Live agent duel: capped per day, cached 1 h, 2 concurrent; `/api/demo/run`: FAST only (no model), same rate limits.

## Log review (11.11.2026)

`ToolCall` rows: tool, ms, ok, error code. `llm.chat` logs model, tokens, ms — never messages. Lab log: ids, diffs of
cards, metrics, gate reasons — no prompt, no transcript, no key. Traces published on the page contain tool
arguments (ODSQL on public data) and truncated public results; no key, no prompt.

## Public surface

No administrative endpoint is public: Django admin binds to 127.0.0.1; there is no route to start an experiment
or approve a promotion. The public API is read-only.
