# Context Compiler — Huwise

Compiles a Huwise / Opendatasoft data portal (Explore API v2.1) into **context for AI agents**:
one short card per dataset, a search index (Elasticsearch), a graph of joinable datasets (Neo4j),
an MCP server with three tools — and an evaluation harness that **proves with numbers** that agents
answer better with the compiled context than with raw catalog access.

Development portal: `data.education.gouv.fr` (French Ministry of Education).

Status: in development. Plan (in Russian): [`docs/PLAN.md`](docs/PLAN.md).

## Branches

`feat/*` → `dev` (development) → `preprod` (verified) → `prod` (stable, default).

Stack (same as Huwise): Django + DRF, MariaDB, Celery + RabbitMQ, Elasticsearch, Neo4j, MCP Python SDK.

## Run locally

```bash
docker compose up -d --wait          # MariaDB, RabbitMQ, Elasticsearch, Neo4j on 127.0.0.1
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt   # needs libmariadb-dev, pkg-config
cp .env.example .env
.venv/bin/python manage.py migrate
.venv/bin/python manage.py test
```
