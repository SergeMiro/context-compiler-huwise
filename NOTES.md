# Notes (what did not go as planned, and why)

## T4 — search quality, BM25 v1 (09.11.2026)

Plan acceptance «"collèges publics Côte-d'Or" → `fr-en-annuaire-education` in top-3» is **not met** by plain BM25.

- The directory's title is «Annuaire de l'éducation»: no "école/collège" in it, while ~100 datasets have
  "collèges"/"écoles" in their titles. Lexical search prefers them.
- Tried: `best_fields` / `most_fields` / `cross_fields`, with and without fuzziness, with a `log1p(records_count)`
  boost. Best: `cross_fields` without fuzziness (kept). Fuzziness made "Côte-d'Or" match «Livre d'or».
- A kept `synonyms` edit lifts the directory to top-5 for 2 of 3 directory questions (4th, 5th).
- Gotcha fixed: a separate `synonyms` field gets near-zero IDF (BM25 computes IDF only over documents that have the
  field). Synonyms are now extra values of `title`.

Decision: keep BM25 for now (k=5 cards go to the agent, which chooses). The eval (T12) measures `find@5`;
dense vectors are added only if that number shows recall is the bottleneck. This failing question is the demo case
for the improve loop. Golden cases may accept several valid datasets (e.g. `fr-en-carte-scolaire-colleges-publics`
also lists public collèges).

## T8b — usage signals from the portal's own MCP log (09.11.2026)

`data.education.gouv.fr` publishes `analyse-usage-mcp-et-agent-ia-copie`: one row per call that AI agents made to
its Huwise MCP server (Huwy + "Connecter votre IA"), Feb → Nov 2026, 39 675 rows. Most used: the directory
`fr-en-annuaire-education` (3 389 calls), then geolocation (2 186), bac by academy (1 006). Top catalog searches:
"éducation", "indice de position sociale", "IPS", "collège", "résultats brevet", "collèges Poissy".

`manage.py signals <domain>` loads calls per dataset (1 request, group_by) into `Dataset.usage_count`; compiled
search adds `0.05 * sqrt(usage_count)` to BM25 (naked baseline does not).

Probe set (11 questions, not reused in the golden set): top-1 / top-5
- BM25 only: 7 / 9 — the directory missing for "collèges publics Côte-d'Or" and "combien d'écoles en France"
- + usage (`sqrt`, sum, 0.05): **8 / 11**
- `log2p` multiply: 7 / 10; `log1p` sum: 8 / 10

Risk: tuned on 11 questions; the golden-set eval (T12) is the real check.

## T11 — what the golden set taught (09.11.2026)

Writing reference queries by hand failed 11 times out of 30 on the first run — the same traps an agent falls into:
- **Years are `date` fields** in 9 datasets (`session`, `rentree_scolaire`, `annee`): `session='2025'` → API error
  "Incompatible types… date vs text"; `year(session)=2025` works. Full cards now say so for every date field.
- **One department, three formats:** Côte-d'Or is `'021'` (annuaire, bac par département, DNB), `'21'`
  (IPS `code_du_departement`, écoles effectifs) and `"COTE D'OR"` as a label. Cards show sample values of key fields.
- **Numbers stored as text:** `ips` in IPS écoles / `ips_etab` in IPS lycées are `text`: `avg()` fails, `order_by desc`
  sorts lexicographically. Those questions were replaced (collèges: numeric `ips`).
- `academie='DIJON'` in IPS/bac datasets vs `libelle_academie='Dijon'` in the directory.

## T15 — from zero (09.11.2026)

`docker compose down -v && scripts/bootstrap.sh` → 314 datasets, 6 976 fields, 314 cards, 310 with usage,
30 golden answers, 314 pages in `out/`, in **85 s**. bench right after: find p95 24 ms, explain p95 47 ms (cold);
warm: 15 / 26 ms.

Open: the real `naked` vs `compiled` table needs a model in `.env` (`CTXC_LLM_*`).
