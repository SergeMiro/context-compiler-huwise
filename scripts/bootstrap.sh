#!/usr/bin/env bash
# From zero to a compiled portal: services -> schema -> scan -> usage signals -> cards -> ES + Neo4j -> golden answers.
set -euo pipefail
cd "$(dirname "$0")/.."
DOMAIN=${1:-data.education.gouv.fr}
PY=.venv/bin/python
docker compose up -d --wait
$PY manage.py migrate -v0
$PY manage.py scan "$DOMAIN" --full
$PY manage.py signals "$DOMAIN"
$PY manage.py compile "$DOMAIN"
$PY manage.py project "$DOMAIN"
$PY manage.py golden_refresh "$DOMAIN" | tail -1
$PY manage.py export_llms "$DOMAIN" "out/$DOMAIN"
$PY manage.py bench "$DOMAIN" -n 100
