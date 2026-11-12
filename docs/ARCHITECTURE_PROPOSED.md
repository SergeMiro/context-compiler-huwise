# Proposed architecture: two layers on top of Huwise

> Nous ne remplaçons pas Huwise. Nous proposons une boucle de mesure et d'optimisation sûre, au-dessus de ses
> outils existants.

The Huwise side of the map (`ctx/architecture.json`) is built only from `docs/HUWISE_SOURCES.md`: every block has a
status (VERIFIED with a verbatim quote and URL, INFERRED, or PROPOSED for ours). Internal storage, ranking,
orchestration and Huwy's model are not public and are not claimed.

```
            Huwise (unchanged)                                   Proposed (this repo)
 sources → ingestion → catalog ─┐                     ┌──────────── Context Optimizer (hot path, no model) ───────────┐
                    storage ────┼─> Explore API ──────┤ cards · recipes · value grounding · router · cache · evidence  │──> agent / user
 Living Context Layer ──────────┘      │              │ drift (schema hash, data version)                              │
 governance (every request) ───────────┘              └───────────────▲───────────────────────────┬────────────────────┘
 Huwise MCP server · Huwy (MCP client)                                │ human promotion           │ eval traces
                                                      ┌───────────────┴──── AutoContext Lab (PREPROD only) ─┐
                                                      │ collect → diagnose → one edit → static check → eval │
                                                      │ → versioned gate → keep / revert → chained log      │
                                                      └─────────────────────────────────────────────────────┘
```

## Layer 1 — Context Optimizer (`optimizer/`)

| function | code | what it does | status |
|---|---|---|---|
| Context extraction & compilation | `sources/explore.py`, `ctx/compile.py` | schema, types, sample values, keys, value formats, query hints, versioned cards | existing, reused |
| Verified query recipes | `optimizer/recipes.py` | "how many <type> [public/private] in <place>" on `fr-en-annuaire-education`; a recipe runs only if every word is understood, every slot resolves to a stored value, and the schema hash of the fields it reads equals the hash it was verified on (`VERIFIED_SCHEMA`) | implemented |
| Value grounding | `optimizer/values.py` | asks the portal (`search(field, …)` + `group_by`) for the exact stored value; ambiguous or missing → no recipe | implemented |
| Adaptive router | `optimizer/router.py` | FAST (recipe, 0 model calls) / STANDARD (agent, 6 steps) / DEEP (comparison, several things asked: 8 steps); deterministic rules, versioned `POLICY_VERSION` | implemented |
| Grounded query | `optimizer/pipeline.py: grounded_query` | the existing validated `tools.query` + cache + on an empty result a hint: `'DIJON' is stored as 'Dijon'`, `codes are written with leading zeros, try '021'` | implemented |
| Smart cache | `optimizer/cache.py` | key = portal + permission scope (HMAC of the client key, never the key) + dataset + schema version + data version + params + recipe; TTL 1 h; per process | implemented (shortcut: per process) |
| Evidence contract | `optimizer/evidence.py` | schema_valid / executed / result_consistent kept apart; semantic correctness explicitly *not* checked at runtime; an answer whose number no query returned is **not stated** (`blocked` → abstention) | implemented |
| Drift & freshness | `recipes.schema_hash`, `cache.data_version` | schema change disables the recipe (route falls back), data version change gives a new cache key | implemented; no scheduled regression job yet |
| Context compression | `optimizer/compress.py` | per-question card trimming, measured by `optimizer_check` (field retention, token savings) | measured, **not enabled** (retention too low) |
| Parallel tool plan | — | FAST plan is fixed in advance; agent-side parallelism not implemented | not done |

Online path stays light: no LLM judge, no regeneration, no experiment on a user request. A FAST answer is one or two
value lookups (cached) and one count query.

## Layer 2 — AutoContext Lab (`lab/`)

Builds on `evals/improve.py` and adds what makes it safe to run unattended:

1. **COLLECT** failures of the base run, dev split only (`EvalCase.split`); holdout cases are excluded in both
   `propose` and the control sample of `apply_edit`.
2. **DIAGNOSE** each failure deterministically: `wrong_asset`, `schema_mismatch`, `wrong_filter`,
   `hallucinated_value`, `latency`, `permission_error`, `no_answer` (`lab/cycle.py: diagnose`).
3. **HYPOTHESIZE** one card edit per failing dataset (existing proposer).
4. **FORK**: `guard()` refuses to run unless `CTXC_ENV=preprod` (own database `ctxc_preprod`, ES alias
   `cards_preprod`; the shared Neo4j graph is read-only there). `apply_edit` calls the same guard.
5. **PATCH** only allowed artifacts (`lab/policy.json: editable_artifacts`).
6. **STATIC CHECK**: query templates validated against the schema, no links/instructions, no golden expected value
   copied into the edit.
7. **EVAL** failing + control cases, same model and configuration as the base run.
8. **QUALITY GATE** from `lab/policy.json` (versioned, fixed before runs): ≥ 1 fixed, 0 control broken, 0 new
   confident wrong answers, tokens ≤ +25 %.
9. **KEEP / REVERT**: revert = recompile the card without the edit and re-index.
10. **REPORT**: `lab/log.py` append-only JSONL with a sha256 chain; `manage.py lab log` verifies it.
11. **PROMOTION**: no endpoint; a human applies the diff in production (see `docs/ROLLBACK.md`).

Budget per cycle: `max_proposals`, `max_llm_calls`, `max_seconds` (`Budget` wrapper raises `BudgetExceeded`).

## New routes, commands, migrations

| kind | name | notes |
|---|---|---|
| route | `GET /api/demo/run?scenario=| route | `GET /api/demo/run?scenario=` | live configuration C, only when the route is FAST (no model); otherwise 409 and the page shows the recording |mode=| route | `GET /api/demo/run?scenario=` | live configuration C, only when the route is FAST (no model); otherwise 409 and the page shows the recording |provider=` | runs the chosen configuration live (C on a FAST route: no model); daily cap, 404/400/503 on bad input |
| static data | `/data/architecture.json`, `/data/scenarios.json`, `/data/comparison.json`, `/data/lab.json`, `/data/legacy.json` | the page's read-only API (the proposed `GET /api/architecture`, `/api/demo/scenarios`, `/api/evals/comparison`, `/api/lab/experiments` as files) |
| command | `eval --mode abc --suite --split` | A/B/C on the same cases |
| command | `record_traces <domain>` | recorded A/B/C traces + simulated scenarios → `ctx/traces/scenarios.json` |
| command | `optimizer_check <domain>` | deterministic checks → `ctx/traces/checks.json` |
| command | `lab run <domain>` / `lab log` | preprod only / prints and verifies the chain |
| migration | `evals/0003_suites_and_optimized` | additive |
| preprod | `.env.preprod` (database `ctxc_preprod`, index `cards_preprod`) | internal only, no public site |

Not implemented on purpose: `POST /api/lab/experiments` and any promotion endpoint (the public demo is read-only).
