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
