"""Static jury showcase (French, English copy under /en/): architecture map, traces, lab, A/B/C comparison.
Everything shown comes from files and the database: ctx/architecture.json (sources in docs/HUWISE_SOURCES.md),
ctx/traces/scenarios.json (record_traces), eval runs (eval --mode abc) and the lab log. Nothing is typed by hand."""
import json
import math
import random
import re
from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string

from catalog.models import Dataset, Field
from ctx.export import export_llms
from evals.models import EvalCase, EvalRun

from .site_text import LIMITS, TEXT

HERE = Path(__file__).parent
LOGOS = HERE / "logos"
STACK = [("python", "Python", "3.12", "#3776AB"), ("django", "Django + DRF", "5.2", "#092E20"),
         ("modelcontextprotocol", "MCP Python SDK", "2.3", "#000000"), ("mariadb", "MariaDB", "11.4", "#003545"),
         ("celery", "Celery", "5.6", "#37814A"), ("rabbitmq", "RabbitMQ", "4.1", "#FF6600"),
         ("elasticsearch", "Elasticsearch", "8.15", "#005571"), ("neo4j", "Neo4j", "5.26", "#4581C3"),
         ("docker", "Docker", "Compose", "#2496ED"), ("traefikproxy", "Traefik", "proxy + TLS", "#24A1C1"),
         ("nginx", "Nginx", "site", "#009639"), ("letsencrypt", "Let's Encrypt", "HTTPS", "#003A70")]


def stack():
    out = []
    for name, label, detail, color in STACK:
        svg = (LOGOS / f"{name}.svg").read_text()
        svg = re.sub(r"<svg[^>]*>", '<svg viewBox="0 0 24 24" aria-hidden="true">', svg)
        out.append({"svg": svg.replace("<title>", "<!--").replace("</title>", "-->"), "label": label,
                    "detail": detail, "color": color})
    return out


def nb(n):
    return f"{n:,}".replace(",", " ")


def triples(portal):
    """Every A/B/C comparison: for each finished optimized run, the closest earlier finished compiled and naked runs
    with the same model, suite, split and n (a re-run C after a crash still pairs with its A and B). Newest first."""
    key = lambda r: (r.metrics.get("suite"), r.metrics.get("split"), r.metrics.get("n"))  # noqa: E731
    done = EvalRun.objects.filter(portal=portal, finished_at__isnull=False)

    def prev(c, mode):
        return next((r for r in done.filter(mode=mode, model=c.model, id__lt=c.id).order_by("-id") if key(r) == key(c)),
                    None)

    def near(c, mode):  # A may be recorded after C (it needs its own key and quota): closest earlier, else first later
        return prev(c, mode) or next((r for r in done.filter(mode=mode, model=c.model, id__gt=c.id).order_by("id")
                                      if key(r) == key(c)), None)
    out = []
    for c in done.filter(mode="optimized").order_by("-id"):
        a, b = prev(c, "naked"), prev(c, "compiled")
        if a and b and c.metrics.get("n", 0) > 3:
            h = near(c, "huwise")  # optional: the real Huwise MCP run on the same questions, when one exists
            out.append(((h,) if h else ()) + (a, b, c))
    return sorted(out, key=lambda t: t[-1].metrics.get("split") != "holdout")  # the clean set opens first


def mcnemar(x, y):
    """Exact two-sided McNemar p-value for paired booleans."""
    b = sum(1 for i, j in zip(x, y) if i and not j)
    c = sum(1 for i, j in zip(x, y) if j and not i)
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def boot_ci(x, y, n=2000, seed=13):
    """95 % paired bootstrap CI of mean(y) - mean(x), in percentage points."""
    rnd, idx, diffs = random.Random(seed), range(len(x)), []
    for _ in range(n):
        s = [rnd.choice(idx) for _ in idx]
        diffs.append(100 * sum(y[i] - x[i] for i in s) / len(s))
    diffs.sort()
    return round(diffs[int(.025 * n)], 1), round(diffs[int(.975 * n)], 1)


def pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    i, f = divmod(q * (len(xs) - 1), 1)  # linear interpolation: the median of an even n is the mean of the two middle values
    i = int(i)
    return round(xs[i] + (xs[min(i + 1, len(xs) - 1)] - xs[i]) * f)


def comparison(portal):
    cases = {c.slug: c for c in EvalCase.objects.filter(portal=portal)}
    out = []
    for runs in triples(portal):
        modes = [r.mode for r in runs]
        slugs = [s for s in runs[-1].metrics["per_case"] if all(s in r.metrics["per_case"] for r in runs)]
        per = {r.mode: r.metrics["per_case"] for r in runs}
        ok = {m: [int(per[m][s]["answer_ok"]) for s in slugs] for m in modes}
        summary = {}
        for r in runs:
            pc = [per[r.mode][s] for s in slugs]
            ms = [v.get("ms", 0) for v in pc]
            summary[r.mode] = {
                "run": r.id, "accuracy": round(100 * sum(ok[r.mode]) / len(slugs), 1),
                "dataset_ok": r.metrics.get("dataset_ok"), "first_try": r.metrics.get("odsql_first_try"),
                "p50": pct(ms, .5), "p95": pct(ms, .95), "tokens": sum(v.get("tokens", 0) for v in pc),
                "llm_calls": sum(v.get("llm_calls", 0) for v in pc),
                "wrong_confident": sum(1 for v in pc if not v["answer_ok"] and not v.get("abstained")),
                "verified": round(100 * sum(v.get("evidence") == "verified" for v in pc) / len(pc), 1),
                "routes": r.metrics.get("routes") or {}}
        diffs = {f"{y}-{x}": {"ci": boot_ci(ok[x], ok[y]), "p": round(mcnemar(ok[x], ok[y]), 3),
                              "pp": round(100 * (sum(ok[y]) - sum(ok[x])) / len(slugs), 1)}
                 for x, y in (("huwise", "compiled"), ("huwise", "optimized"), ("naked", "compiled"),
                              ("compiled", "optimized"), ("naked", "optimized")) if x in modes}
        rows = [{"slug": s, "q": cases[s].question if s in cases else s, "tags": cases[s].tags if s in cases else [],
                 "split": cases[s].split if s in cases else "",
                 **{m: {k: per[m][s].get(k) for k in ("answer_ok", "route", "evidence", "ms", "tokens", "llm_calls",
                                                      "abstained")} for m in modes}} for s in slugs]
        a = runs[-1]
        out.append({"suite": a.metrics.get("suite"), "split": a.metrics.get("split"), "n": len(slugs),
                    "model": a.model, "date": a.finished_at.strftime("%d.%m.%Y"), "modes": modes,
                    "commit": a.metrics.get("commit", ""), "runs": [r.id for r in runs],
                    "summary": summary, "diffs": diffs, "rows": rows})
    return out


def legacy_pairs(portal):
    """The earlier internal naked/compiled experiments, shown as history only."""
    full = EvalCase.objects.filter(portal=portal, suite="education").count()
    seen, out = set(), []
    for c in EvalRun.objects.filter(portal=portal, mode="compiled", finished_at__isnull=False).order_by("-id"):
        n = EvalRun.objects.filter(id=c.id - 1, mode="naked", model=c.model).first()
        if n and n.metrics.get("n") == c.metrics.get("n") == full and c.model not in seen and not c.metrics.get("suite"):
            seen.add(c.model)
            out.append({"model": c.model, "naked": n.metrics.get("answer_ok"), "compiled": c.metrics.get("answer_ok"),
                        "runs": [n.id, c.id], "date": c.finished_at.strftime("%d.%m.%Y")})
    return out


def lab_data():
    from lab import log
    rows = log.read()
    ok, bad = log.verify(rows)
    return {"chain_ok": ok, "bad_line": bad, "entries": [r["entry"] | {"sha": r["sha"][:12]} for r in rows],
            "policy": json.loads((Path(settings.BASE_DIR) / "lab" / "policy.json").read_text())}


def build_site(portal, out_dir):
    out = Path(out_dir)
    pages = export_llms(portal, out)
    arch = json.loads((HERE / "architecture.json").read_text())
    traces_file = HERE / "traces" / "scenarios.json"
    scenarios = json.loads(traces_file.read_text()) if traces_file.exists() else {}
    checks_file = HERE / "traces" / "checks.json"
    checks = json.loads(checks_file.read_text()) if checks_file.exists() else None
    if checks:
        checks["meta_ok"] = sum(m["holds"] is True for m in checks["metamorphic"])
    data = {"architecture": arch, "scenarios": scenarios, "comparison": comparison(portal),
            "legacy": legacy_pairs(portal), "lab": lab_data(), "checks": checks}
    (out / "data").mkdir(parents=True, exist_ok=True)
    for name, value in data.items():  # the read-only "API" of the page: /data/<name>.json
        (out / "data" / f"{name}.json").write_text(json.dumps(value, ensure_ascii=False, default=str), encoding="utf-8")
    import llm
    names = {"openrouter": "OpenRouter", "nim": "NVIDIA NIM"}
    providers = [p | {"label": f"{names.get(p['name'], p['name'])} · {p['model'].split('/')[-1].split(':')[0]}"}
                 for p in llm.public_providers()]  # names and models only, never keys
    base = {"domain": portal.domain, "pages": pages, "stack": stack(), "live_model": settings.CTXC_LLM_MODEL,
            "providers": providers,
            "datasets": nb(Dataset.objects.filter(portal=portal).count()),
            "fields": nb(Field.objects.filter(dataset__portal=portal).count()),
            "data_json": json.dumps(data, ensure_ascii=False, default=str).replace("</", "<\\/"),
            "env": settings.CTXC_ENV, "cmp": data["comparison"], "legacy": data["legacy"], "lab": data["lab"],
            "checks": checks}
    for lang, path in (("fr", out / "index.html"), ("en", out / "en" / "index.html")):
        path.parent.mkdir(parents=True, exist_ok=True)
        t = {k: v[lang] if isinstance(v, dict) else v for k, v in TEXT.items()}
        path.write_text(render_to_string("ctx/site.html", base | {"lang": lang, "t": t, "t_json": json.dumps(t, ensure_ascii=False),
                                                                  "limits": [x[lang] for x in LIMITS],
                                                                  "root": "" if lang == "fr" else "../"}),
                        encoding="utf-8")
    return pages

