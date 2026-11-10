# Demo (5 minutes)

Prepared stand: `scripts/bootstrap.sh` done, a model set in `.env`, `manage.py runserver 127.0.0.1:8797` running.

1. **Scan.** `manage.py scan data.education.gouv.fr --full` → `314 datasets, 6976 fields`, 2 requests, ~10 s (samples already taken).
2. **A card.** `/admin/catalog/dataset/` sorted by usage → `fr-en-annuaire-education` (3 389 agent calls in the
   portal's MCP log). Show the short card: `code_departement (e.g. '059')`.
3. **One question, two agents.** `manage.py eval data.education.gouv.fr --mode both --cases colleges-publics-cote-dor,ips-moyen-colleges-cote-dor,bac-admis-cote-dor-2025`
   — the naked agent has to guess `'21'` vs `'021'` and `year(session)`; the compiled one reads them on the card.
   ⏱ ~2.5 min with the free model: start it before talking about the card (rehearsal 10.11: naked 1/3, compiled 2/3).
4. **The table.** Do not run it live (30 questions × 2 ≈ 1.5–2 h on the free model): open <https://context.smiro.dev/>
   — naked 30 % → compiled 80 % correct, right dataset 53 → 83 %, tokens +2 %. What still fails: `NOTES.md` T17.
5. **Improve.** `manage.py improve data.education.gouv.fr --mode propose --max-edits 3` (~15 s, uses the last compiled run) → `/admin/ctx/contextedit/` → diff →
   "Approve: test on the golden set" → kept / reverted with fixed / broken cases.
6. **Graph and llms.txt.** `explain_dataset` → `joinable` by `uai`, `code_departement`…; `out/<domain>/llms.txt`.
7. **Scale in one sentence.** From 1 to 5 000 portals nothing changes in the code: database size, workers, ES
   routing, cache.

Live: <https://context.smiro.dev/> (showcase with the eval table) and `https://context.smiro.dev/mcp` (connect
Claude, ask « Combien de collèges publics en Côte-d'Or ? »).

Fallback without a model: `scripts/mcp_smoke.py` (find → explain → 58, and the rejected `departement='21'` with
"similar fields: code_departement").
