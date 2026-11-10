"""Static showcase of a portal (French): index.html + eval.json (recorded agent duel) + llms.txt + datasets/*.md.
Everything comes from the database; the "relancer en direct" button calls /api/agent on the MCP server."""
import json
from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string

from catalog.models import Dataset, Field
from ctx.export import export_llms
from evals.golden import NO_DATA
from evals.models import EvalResult, EvalRun
from evals.runner import condense

# the four examples on the page, one story each; the texts describe the transcripts of STORIES_RUNS and are shown
# only for that pair (a newer eval keeps the labels and drops the texts until they are rewritten)
STORIES_RUNS = (10, 11)
STORIES = [
    {"slug": "eleves-colleges-paris-2025", "label": "Le piège du format",
     "naked": "Quatre requêtes refusées par l'API : l'année est stockée comme une date, pas comme du texte. "
              "Puis « Paris » au lieu de « PARIS » : 0 ligne. Plus d'étapes, pas de réponse.",
     "compiled": "La fiche montre le format : year(rentree_scolaire)=2025 et departement='PARIS'. Juste du premier coup."},
    {"slug": "lycees-prives-academie-dijon", "label": "Perdu dans le catalogue",
     "naked": "Deux recherches sans trouver l'annuaire : son titre ne dit ni « lycée » ni « école ». "
              "Il prend un autre jeu, devine un code d'académie et trouve 0 ligne.",
     "compiled": "L'annuaire arrive en tête : c'est le jeu que les agents utilisent le plus sur ce portail. "
                 "Une recherche, une requête : 47."},
    {"slug": "departement-plus-colleges-prives", "label": "Faux mais sûr de lui",
     "naked": "Prend le mauvais jeu de données et répond « le Nord » avec assurance. La bonne réponse est Paris.",
     "compiled": "Trouve l'annuaire, compte les collèges privés par département : Paris, 103."},
    {"slug": "academie-plus-ecoles", "label": "Abandonne trop tôt",
     "naked": "Trois requêtes refusées sur le format de l'année, puis il conclut « pas de données ». "
              "Les données existent.",
     "compiled": "Une requête groupée par académie sur l'annuaire : Versailles, 3 353 écoles."},
]
METRICS = [("answer_ok", "Réponse correcte", "%"), ("dataset_ok", "Bon jeu de données", "%"),
           ("odsql_first_try", "Requête valide du 1er coup", "%")]
# (logo file, label, detail, brand colour, colour on dark background) — the stack strip under the architecture
STACK = [("python", "Python", "3.12", "#3776AB", "#6fa8dc"), ("django", "Django + DRF", "5.2", "#092E20", "#44B78B"),
         ("mariadb", "MariaDB", "11.4", "#003545", "#C49A6C"), ("celery", "Celery", "5.6", "#37814A", "#8dc63f"),
         ("rabbitmq", "RabbitMQ", "4.1", "#FF6600", "#FF6600"), ("elasticsearch", "Elasticsearch", "8.15", "#005571", "#00BFB3"),
         ("neo4j", "Neo4j", "5.26", "#4581C3", "#6fa3e0"), ("modelcontextprotocol", "MCP Python SDK", "2.3", "#000000", "#e7ebf3"),
         ("docker", "Docker", "Compose", "#2496ED", "#2496ED"), ("traefikproxy", "Traefik", "proxy + TLS", "#24A1C1", "#24A1C1"),
         ("nginx", "Nginx", "site statique", "#009639", "#3ecf6e"), ("letsencrypt", "Let's Encrypt", "HTTPS", "#003A70", "#FFA400")]
LOGOS = Path(__file__).parent / "logos"


def stack():
    import re
    out = []
    for name, label, detail, light, dark in STACK:
        svg = (LOGOS / f"{name}.svg").read_text()
        svg = re.sub(r"<svg[^>]*>", '<svg viewBox="0 0 24 24" aria-hidden="true">', svg).replace("<title>", "<!--").replace("</title>", "-->")
        out.append({"svg": svg, "label": label, "detail": detail, "light": light, "dark": dark})
    return out




def nb(n):
    return f"{n:,}".replace(",", " ")


def stories_for(run_ids, slugs):
    same = tuple(run_ids) == STORIES_RUNS
    return [st if same else {"slug": st["slug"], "label": st["label"]} for st in STORIES if st["slug"] in slugs]


def latest_pair(portal):
    """Latest `eval --mode both` over the full golden set: a compiled run right after a naked run of the same model
    (same cards, same harness), or None."""
    full = portal.eval_cases.count()
    for c in EvalRun.objects.filter(portal=portal, mode="compiled", finished_at__isnull=False).order_by("-id"):
        n = EvalRun.objects.filter(portal=portal, id=c.id - 1, mode="naked", model=c.model).first()
        if n and n.metrics.get("n") == c.metrics.get("n") == full:
            return n, c
    return None


def _expected(case):
    return "pas de données" if case.expected_value == NO_DATA else case.expected_value


def _row(result, run):
    per = run.metrics.get("per_case", {}).get(result.case.slug, {})
    return {"answer": result.answer, "answer_ok": result.answer_ok, "dataset_ok": per.get("dataset_ok", False),
            "found_dataset": result.found_dataset, "steps": result.steps, "ms": result.ms, "tokens": result.tokens,
            "trace": condense(result.transcript)}


def duel_data(pair):
    naked, compiled = pair
    by = {r.case_id: r for r in EvalResult.objects.filter(run=naked).select_related("case")}
    cases = []
    for r in EvalResult.objects.filter(run=compiled).select_related("case").order_by("case_id"):
        if r.case_id in by:
            c = r.case
            cases.append({"slug": c.slug, "question": c.question, "tags": c.tags, "expected": _expected(c),
                          "naked": _row(by[r.case_id], naked), "compiled": _row(r, compiled)})
    stories = stories_for((naked.id, compiled.id), {c["slug"] for c in cases})
    return {"model": compiled.model, "date": compiled.finished_at.strftime("%d.%m.%Y"), "runs": [naked.id, compiled.id],
            "stories": stories, "cases": cases}


def build_site(portal, out_dir):
    out = Path(out_dir)
    pages = export_llms(portal, out)
    pair = latest_pair(portal)
    if pair:
        (out / "eval.json").write_text(json.dumps(duel_data(pair), ensure_ascii=False), encoding="utf-8")
    bars = [{"label": label, "naked": pair[0].metrics.get(k) or 0, "compiled": pair[1].metrics.get(k) or 0}
            for k, label, _ in METRICS] if pair else []
    ctx = {
        "domain": portal.domain, "pages": pages, "pair": pair, "bars": bars, "stack": stack(),
        "live_model": settings.CTXC_LLM_MODEL,
        "datasets": nb(Dataset.objects.filter(portal=portal).count()),
        "fields": nb(Field.objects.filter(dataset__portal=portal).count()),
        "steps": [pair[0].metrics.get("steps_avg"), pair[1].metrics.get("steps_avg")] if pair else None,
        "tokens_pct": round(100 * (pair[1].metrics["tokens"] - pair[0].metrics["tokens"]) / pair[0].metrics["tokens"])
        if pair and pair[0].metrics.get("tokens") else None,
    }
    (out / "index.html").write_text(render_to_string("ctx/site.html", ctx), encoding="utf-8")
    return pages
