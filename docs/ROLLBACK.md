# Promotion and rollback

## Promote a kept lab candidate (human, production)

1. Read the candidate in the preprod log: `set -a; . ./.env.preprod; set +a; .venv/bin/python manage.py lab log`
   (chain must say OK), and the edit with its gate reasons in preprod admin (`ContextEdit`, status `kept`).
2. Check the measurements: the edit's `eval_after` (fixed, broken, gate) and, before promoting several edits, a
   holdout run in preprod: `manage.py eval data.education.gouv.fr --mode abc --suite education_v2 --split holdout`.
3. In production (`.env`), create the same edit by hand in Django admin (`ContextEdit`, source `human`, status
   `kept`, same kind and text). There is no automated copy on purpose.
4. `manage.py compile data.education.gouv.fr && manage.py project data.education.gouv.fr` — a new card version is
   created only for the changed dataset.
5. Canary: run the affected golden cases in production
   (`manage.py eval data.education.gouv.fr --mode compiled --cases <slugs>`) and watch `ToolCall` error codes.

## Roll back a card

Card versions are immutable. To go back:

```bash
# production
.venv/bin/python manage.py shell -c "
from ctx.models import ContextEdit; e = ContextEdit.objects.get(id=<ID>); e.status = 'reverted'; e.save()"
.venv/bin/python manage.py compile data.education.gouv.fr   # card re-rendered without the edit (new version)
.venv/bin/python manage.py project data.education.gouv.fr
```

## Roll back the showcase or the code

- Showcase: `site/` is generated; rebuild from the previous commit (`git checkout <sha> -- ctx/` then
  `build_site data.education.gouv.fr site`), nginx serves it live.
- MCP server: `git checkout prod~1 && docker compose --profile public up -d --build mcp`.
- Preprod has no public site since 12.11.2026 (internal only). It can be removed entirely without touching
  production: drop `ctxc_preprod` and the `cards_preprod_*` index.

## Rollback drill (11.11.2026, preprod)

A recipe disabled by schema drift and a cache invalidated by a new data version were exercised as simulated
scenarios (`record_traces --only drift,stale-cache`): both changes ran inside a rolled-back transaction on the
preprod database; the recipe fell back to the agent path and the cache key changed. See `ctx/traces/scenarios.json`.
