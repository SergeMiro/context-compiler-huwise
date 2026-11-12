"""Deterministic checks of the Context Optimizer (no model): recipe coverage and accuracy, metamorphic relations,
compression retention, FAST-path latency cold vs warm. -> ctx/traces/checks.json (shown on the page as RECORDED)."""
import json
import re
import statistics
import time
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from catalog.models import Dataset, Portal
from ctx.compile import current
from evals.models import EvalCase
from evals.runner import answer_ok
from optimizer import cache, compress, pipeline, router
from optimizer.values import candidates

OUT = Path(__file__).resolve().parents[3] / "ctx" / "traces" / "checks.json"
IDENT = re.compile(r"`?([A-Za-z_][A-Za-z0-9_]*)`?")


class Command(BaseCommand):
    help = "Deterministic optimizer checks (Explore API calls, no model)"

    def add_arguments(self, p):
        p.add_argument("domain")

    def handle(self, domain, **_):
        portal = Portal.objects.get(domain=domain)
        out = {"recorded_at": timezone.now().isoformat(timespec="seconds"), "recipes": {}, "metamorphic": [],
               "compression": {}, "latency": {}}
        for suite in ("education", "education_v2"):
            cases = list(EvalCase.objects.filter(portal=portal, suite=suite))
            fast = ok = 0
            for c in cases:
                r = router.route(domain, c.question)
                if r["route"] == "FAST":
                    fast += 1
                    ok += answer_ok(c, pipeline.answer(domain, c.question)["answer"])
            out["recipes"][suite] = {"n": len(cases), "fast": fast, "fast_correct": ok}
            self.stdout.write(f"recipes {suite}: {fast}/{len(cases)} FAST, {ok} correct")
        # metamorphic: public <= all and public + private <= all, same place, same dataset, same moment
        for place in ["à Dijon", "à Lyon", "en Côte-d'Or", "dans l'académie de Rennes", "en Bretagne", "à Toulouse"]:
            for t in ("collèges", "lycées", "écoles"):
                n = {}
                for s in ("", " publics", " privés"):
                    r = pipeline.answer(domain, f"Combien de {t}{s} {place} ?")
                    n[s.strip() or "all"] = (r["queries"][0]["result"]["total_count"] if r["route"] == "FAST" else None)
                holds = None if None in n.values() else (n["publics"] <= n["all"] and n["publics"] + n["privés"] <= n["all"])
                out["metamorphic"].append({"q": f"{t} {place}", **n, "holds": holds})
        bad = [m for m in out["metamorphic"] if m["holds"] is False]
        self.stdout.write(f"metamorphic: {sum(m['holds'] is True for m in out['metamorphic'])} hold, {len(bad)} violated")
        # compression retention on cases with a reference query
        kept = total = 0
        saved, misses = [], []
        for c in EvalCase.objects.filter(portal=portal).exclude(expected_datasets=[]):
            ds = Dataset.objects.filter(portal=portal, dataset_id=c.expected_datasets[0]).first()
            card = current(ds) if ds else None
            if not card or not c.reference_odsql:
                continue
            fields = set(ds.fields.values_list("name", flat=True))
            need = {m for v in c.reference_odsql.values() if isinstance(v, str) for m in IDENT.findall(v)} & fields
            small, tok = compress.compress(card.full, c.question)
            got = compress.kept_fields(small)
            total += 1
            kept += need <= got
            if not need <= got:
                misses.append({"slug": c.slug, "missing": sorted(need - got)})
            saved.append(100 * (card.tokens_full - tok) / card.tokens_full)
        out["compression"] = {"cases": total, "all_needed_fields_kept": kept,
                              "tokens_saved_median_pct": round(statistics.median(saved), 1) if saved else None,
                              "misses": misses[:20]}
        self.stdout.write(f"compression: {kept}/{total} keep every needed field, median -{out['compression']['tokens_saved_median_pct']} % tokens")
        # FAST latency: cold (cache cleared) vs warm, same question
        q = "Combien y a-t-il de collèges à Dijon ?"
        cold, warm = [], []
        for _ in range(10):
            cache.CACHE.items.clear()
            candidates.cache_clear()
            t = time.monotonic(); pipeline.answer(domain, q); cold.append((time.monotonic() - t) * 1000)
            t = time.monotonic(); pipeline.answer(domain, q); warm.append((time.monotonic() - t) * 1000)
        p = lambda xs, k: round(sorted(xs)[min(len(xs) - 1, int(round(k * (len(xs) - 1))))])  # noqa: E731
        out["latency"] = {"question": q, "runs": 10, "cold_p50_ms": p(cold, .5), "cold_p95_ms": p(cold, .95),
                          "warm_p50_ms": p(warm, .5), "warm_p95_ms": p(warm, .95),
                          "note": "cold = query cache and value-lookup cache cleared before the call; warm = same question again"}
        self.stdout.write(f"latency FAST: cold p50 {out['latency']['cold_p50_ms']} ms, warm p50 {out['latency']['warm_p50_ms']} ms")
        OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
        self.stdout.write(f"-> {OUT}")
