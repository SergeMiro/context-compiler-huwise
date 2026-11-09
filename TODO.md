# TODO (next session)

Read first: `README.md`, `docs/PLAN.md` (rules for the agent, branches), `NOTES.md`. Stand: `docker compose up -d --wait`,
data already loaded (else `scripts/bootstrap.sh`). Branches: `feat/*` → `dev` → `preprod` → `prod`, tests green before each step.
Interview: Friday 13.11.2026, 10:00.

## 1. Model and real numbers (blocked on owner's model choice)
- [ ] Owner picks a model → `.env`: `CTXC_LLM_BASE_URL`, `CTXC_LLM_API_KEY`, `CTXC_LLM_MODEL` (no llmfp, no provider in code).
- [ ] `manage.py eval data.education.gouv.fr --mode both` → table naked vs compiled into `NOTES.md` and README.
- [ ] `manage.py improve … --mode auto --max-edits 5` → "proposed / kept / reverted, correct X → Y" into `NOTES.md`.
- [ ] If `find@5` is the bottleneck in the eval: consider dense vectors in ES (only then).

## 2. Static showcase on GitHub Pages
- [ ] `manage.py build_site <domain> site/`: one `index.html` (what it is, architecture, traps found: '021'/'21',
      year(), numbers as text; usage signal story; bench numbers; eval table from the latest EvalRun pair; one card;
      one edit diff) + `llms.txt` + `datasets/*.md` from `export_llms`. Static, no secrets, no JS dependencies needed.
- [ ] Publish from `prod` via `gh-pages` branch or `/docs` (GitHub Actions is disabled on this account → push the
      built files, no workflow). Link from README.

## 3. Live MCP on the VPS (owner decides: opens a service to the internet)
- [ ] `context.smiro.dev` → MCP only (read-only tools), behind the existing reverse proxy, rate limit kept;
      Django admin stays on 127.0.0.1. systemd user units for `manage.py mcp` (+ celery worker -B).
- [ ] Smoke: `scripts/mcp_smoke.py https://context.smiro.dev/mcp`; connect Claude to it for the demo.

## 4. Demo prep
- [ ] Rehearse `DEMO.md` end to end; fallback without network = screenshots in `site/`.
- [ ] Add a LICENSE (owner's choice; public repo without one = all rights reserved).
