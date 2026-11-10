# TODO (next session)

Read first: `README.md`, `docs/PLAN.md` (rules for the agent, branches), `NOTES.md`. Stand: `docker compose up -d --wait`,
data already loaded (else `scripts/bootstrap.sh`). Branches: `feat/*` → `dev` → `preprod` → `prod`, tests green before each step.
Interview: Friday 13.11.2026, 10:00.

## 1. Eval
- [x] Model: `nvidia/nemotron-3-ultra-550b-a55b:free` 30 % → 80 % (T17); owner switched to `openai/gpt-5.4-mini` 40 % → 90 % (T20).
- [x] 10.11 back to a free model, owner's choice "fast first": `nvidia/nemotron-3.5-super-vl:free` (3/3 compiled on a probe, median ~19 s; lightning 1/3 and not faster), key with a $0 limit.
- [ ] Full `eval --mode both` on super-vl when the free quota allows (~300 requests) → NOTES, site (stories: rewrite for the new runs).
- [ ] Fresh `eval --mode both` with the last-step-without-tools harness and the new card hints → NOTES, README,
      `build_site` (the site picks the latest `both` pair by itself).
- [ ] `improve … --mode auto --max-edits 5` → "proposed / kept / reverted" into NOTES (quota: ~30 requests per edit).

## 2–3. Done 10.11: https://context.smiro.dev/ (showcase) and /mcp (live MCP), see README "Public deployment".
After any eval: `manage.py build_site data.education.gouv.fr site/` (nginx serves the folder, no restart).

## 4. Demo prep
- [ ] Rehearse `DEMO.md` end to end; fallback without network = screenshots in `site/`.
- [x] LICENSE: MIT.
