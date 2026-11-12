"""Record the demo scenarios: A (real Huwise MCP), 0 (generic tools), B (cards), C (cards + optimizer) on the same question, same model,
real Explore API; simulated scenarios run the optimizer against a deliberate fixture. -> ctx/traces/scenarios.json"""
import json
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

import llm
import tools
from catalog.models import Dataset, Field, Portal
from evals import runner
from evals.golden import NO_DATA
from evals.runner import answer_ok, condense
from optimizer import cache, evidence, pipeline, router
from optimizer.scenarios import SCENARIOS

OUT = Path(__file__).resolve().parents[3] / "ctx" / "traces" / "scenarios.json"


class Rollback(Exception):
    pass


def expected(domain, ref):
    if ref is None:
        return NO_DATA
    params = {k: ref[k] for k in ("select", "where") if k in ref}
    params["limit"] = 1 if "answer" in ref else 0
    portal = Portal.objects.get(domain=domain)
    res = tools._records(portal, ref["dataset"], params, None)
    return res["results"][0][ref["answer"]] if "answer" in ref else res["total_count"]


def public(res, question, exp):
    case = SimpleNamespace(expected_value=exp, question=question, tolerance=0.01)
    queries = [{"dataset_id": q["dataset_id"], "params": q.get("params"), "ok": q["ok"],
                "result": evidence._short(q.get("result"))} for q in res["queries"]]
    return {"answer": res["answer"], "answer_ok": answer_ok(case, res["answer"]), "route": res.get("route", "AGENT"),
            "reasons": res.get("reasons", []),
            "evidence": res.get("evidence") or evidence.check(question, res["answer"], res["queries"]),
            "spans": res["spans"], "steps": res["steps"], "tokens": res["tokens"], "ms": res["ms"],
            "llm_calls": res.get("llm_calls", res["steps"]), "trace": condense(res.get("transcript") or []),
            "queries": queries}


class Command(BaseCommand):
    help = "Record demo traces (preprod; calls the model for A and B and for C when it is not FAST)"

    def add_arguments(self, p):
        p.add_argument("domain")
        p.add_argument("--only", default="", help="comma-separated scenario ids")

    def handle(self, domain, only, **_):
        out = json.loads(OUT.read_text()) if OUT.exists() else {}
        wanted = {s for s in only.split(",") if s}
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        for s in SCENARIOS:
            if wanted and s["id"] not in wanted:
                continue
            q = s["question"]
            exp = expected(domain, s.get("ref")) if s["kind"] == "recorded" else expected(domain, SCENARIOS[0]["ref"])
            row = {"id": s["id"], "kind": s["kind"], "question": q, "expected": exp, "title": s["title"],
                   "recorded_at": timezone.now().isoformat(timespec="seconds"), "commit": commit,
                   "model": llm.model_name(), "fixture": s.get("fixture"), "runs": {}}
            if s["kind"] == "recorded":
                for mode in ("huwise", "naked", "compiled", "optimized"):  # huwise = real Huwise MCP (A)
                    try:
                        res = runner._run(domain, q, mode, None)  # same provider-outage retries as the evals
                    except Exception as e:  # keep what was recorded; the page shows "not recorded" for this one
                        self.stdout.write(f"{s['id']} {mode}: FAILED {type(e).__name__}")
                        continue
                    row["runs"][mode] = public(res, q, exp)
                    self.stdout.write(f"{s['id']} {mode}: ok={row['runs'][mode]['answer_ok']} "
                                      f"route={row['runs'][mode]['route']} {res['ms']} ms")
            else:
                row["runs"]["optimized"] = getattr(self, f"sim_{s['id'].replace('-', '_')}")(domain, q, exp)
                self.stdout.write(f"{s['id']}: {row['runs']['optimized']['route']}")
            out[s["id"]] = row
            OUT.parent.mkdir(parents=True, exist_ok=True)  # saved after every scenario: a 503 later loses nothing
            OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str) + "\n")
        self.stdout.write(f"-> {OUT}")

    def sim_drift(self, domain, q, exp):
        before = router.route(domain, q)
        try:
            with transaction.atomic():  # local catalog copy only, rolled back
                Field.objects.filter(dataset__portal__domain=domain, dataset__dataset_id="fr-en-annuaire-education",
                                     name="nom_commune").update(type="int")
                after = router.route(domain, q)
                raise Rollback
        except Rollback:
            pass
        spans = [{"name": "route", "ms": 0, "route": before["route"], "note": "before: schema as verified"},
                 {"name": "route", "ms": 0, "route": after["route"], "note": "after: nom_commune type changed"}]
        return {"answer": "La recette est désactivée ; la question repart par le chemin agent (STANDARD).",
                "answer_ok": None, "route": after["route"], "reasons": after["reasons"], "spans": spans,
                "evidence": {"status": "unverified", "reasons": ["not answered in the simulation"]}, "steps": 0,
                "tokens": 0, "ms": 0, "llm_calls": 0, "trace": [], "queries": []}

    def sim_stale_cache(self, domain, q, exp):
        ds = Dataset.objects.get(portal__domain=domain, dataset_id="fr-en-annuaire-education")
        r1 = pipeline.answer(domain, q)
        r2 = pipeline.answer(domain, q)
        k1 = cache.key(domain, "public", ds, r1["queries"][0]["params"], r1["evidence"].get("recipe", ""))
        try:
            with transaction.atomic():
                ds.raw_metas = (ds.raw_metas or {}) | {"data_processed": "2099-01-01T00:00:00+00:00"}
                ds.save(update_fields=["raw_metas"])
                r3 = pipeline.answer(domain, q)
                k2 = cache.key(domain, "public", ds, r3["queries"][0]["params"], "")
                raise Rollback
        except Rollback:
            pass
        spans = ([s | {"note": "1st call"} for s in r1["spans"] if s["name"] == "query"]
                 + [s | {"note": "same question again"} for s in r2["spans"] if s["name"] == "query"]
                 + [s | {"note": "after a new data version"} for s in r3["spans"] if s["name"] == "query"])
        return {"answer": r3["answer"], "answer_ok": True, "route": "FAST",
                "reasons": [f"cache key changes with the data version: {k1[:12]}… → {k2[:12]}…"], "spans": spans,
                "evidence": r3["evidence"], "steps": 0, "tokens": 0, "ms": r1["ms"] + r2["ms"] + r3["ms"],
                "llm_calls": 0, "trace": [], "queries": r3["queries"]}

    def sim_forbidden(self, domain, q, exp):
        real = tools._http
        tools._http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403, json={})))
        cache.CACHE.items.clear()
        try:
            t = time.monotonic()
            res = pipeline.grounded_query(domain, "fr-en-annuaire-education",
                                          {"where": "nom_commune='Dijon' and type_etablissement='Collège'", "limit": 0})
            ms = int((time.monotonic() - t) * 1000)
        finally:
            tools._http = real
        ev = evidence.check(q, "", [{"dataset_id": "fr-en-annuaire-education", "ok": False, "result": None}])
        return {"answer": "Accès refusé à ce jeu de données : pas de réponse, pas de nombre inventé.",
                "answer_ok": None, "route": "FAST", "reasons": [res.get("error", "")],
                "spans": [{"name": "query", "ms": ms, "ok": False}], "evidence": ev | {"status": "blocked"},
                "steps": 0, "tokens": 0, "ms": ms, "llm_calls": 0, "trace": [], "queries": []}
