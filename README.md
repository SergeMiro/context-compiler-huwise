# Context Compiler — Huwise

Compiles a Huwise / Opendatasoft data portal (Explore API v2.1) into **context for AI agents**:
one short card per dataset, a search index (Elasticsearch), a graph of joinable datasets (Neo4j),
an MCP server with three tools — and an evaluation harness that **proves with numbers** that agents
answer better with the compiled context than with raw catalog access.

Development portal: `data.education.gouv.fr` (French Ministry of Education).

Status: in development. Plan (in Russian): [`docs/PLAN.md`](docs/PLAN.md).

## Branches

`feat/*` → `dev` (development) → `preprod` (verified) → `prod` (stable, default).
