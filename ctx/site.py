"""Static showcase of a portal (French): index.html + eval.json (recorded agent duel) + llms.txt + datasets/*.md.
Everything comes from the database; the page calls /api/* on the MCP server for the live parts."""
import json
from pathlib import Path

from django.template.loader import render_to_string

from catalog.models import Dataset, Field
from ctx.compile import current
from ctx.export import export_llms
from ctx.models import Card, ContextEdit
from evals.golden import NO_DATA
from evals.models import EvalCase, EvalResult, EvalRun
from evals.runner import condense

SHOWCASE_DATASET = "fr-en-annuaire-education"
# duel chips: wins, a "no data" case and one both agents miss (search ranks the directory 2nd) — not only wins
FEATURED = ["lycees-prives-academie-dijon", "classes-ecoles-cote-dor-2024", "eleves-colleges-paris-2025",
            "departement-plus-colleges-prives", "no-data-medecins", "colleges-publics-cote-dor"]
# tool demo: the golden question + the query an agent without context writes (seen in eval transcripts)
TRAPS = [
    {"slug": "colleges-publics-cote-dor", "trap": "Format du code", "field": "code_departement",
     "naive": {"where": "code_departement='21' and type_etablissement='Collège' and statut_public_prive='Public'"},
     "why": "Dans l'annuaire, la Côte-d'Or s'écrit '021'. Sans la fiche, l'agent écrit '21' et trouve 0 collège."},
    {"slug": "bac-admis-cote-dor-2025", "trap": "Année stockée en date", "field": "session",
     "naive": {"select": "sum(nombre_d_admis_a_l_examen) as v", "where": "code_departement='021' and session='2025'"},
     "why": "session est de type date : session='2025' est une erreur de type, year(session)=2025 fonctionne."},
    {"slug": "ips-moyen-colleges-cote-dor", "trap": "Même département, autre format", "field": "code_du_departement",
     "naive": {"select": "avg(ips) as v", "where": "code_du_departement='021' and rentree_scolaire='2025-2026'"},
     "why": "Dans les jeux IPS, le même département s'écrit '21' : le format de l'annuaire ne renvoie rien."},
    {"slug": "lycees-prives-academie-dijon", "trap": "Casse différente", "field": "libelle_academie",
     "naive": {"where": "libelle_academie='DIJON' and type_etablissement='Lycée' and statut_public_prive='Privé'"},
     "why": "Les jeux IPS et bac écrivent 'DIJON', l'annuaire écrit 'Dijon' : la mauvaise casse donne 0 ligne."},
    {"slug": "filles-seconde-gt-2025", "trap": "Champ qui commence par un chiffre", "field": "2ndes_gt_filles",
     "naive": {"select": "sum(2ndes_gt_filles) as v", "where": "year(rentree_scolaire)=2025"},
     "why": "Un nom de champ qui commence par un chiffre s'écrit entre accents graves : `2ndes_gt_filles`."},
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


STATUS_FR = {"proposed": "proposée", "kept": "gardée", "reverted": "annulée", "rejected": "rejetée"}


def nb(n):
    return f"{n:,}".replace(",", " ")


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
    return {"model": compiled.model, "date": compiled.finished_at.strftime("%d.%m.%Y"), "runs": [naked.id, compiled.id],
            "featured": [s for s in FEATURED if any(c["slug"] == s for c in cases)], "cases": cases}


def build_site(portal, out_dir):
    out = Path(out_dir)
    pages = export_llms(portal, out)
    pair = latest_pair(portal)
    if pair:
        (out / "eval.json").write_text(json.dumps(duel_data(pair), ensure_ascii=False), encoding="utf-8")
    cases = {c.slug: c for c in EvalCase.objects.filter(portal=portal)}
    traps = [t | {"question": cases[t["slug"]].question, "dataset": cases[t["slug"]].expected_datasets[0],
                  "odsql": cases[t["slug"]].reference_odsql, "path": cases[t["slug"]].answer_path,
                  "expected": cases[t["slug"]].expected_value} for t in TRAPS if t["slug"] in cases]
    bars = []
    if pair:
        for k, label, unit in METRICS:
            a, b = pair[0].metrics.get(k) or 0, pair[1].metrics.get(k) or 0
            bars.append({"label": label, "naked": a, "compiled": b, "unit": unit})
    ds = Dataset.objects.filter(portal=portal, dataset_id=SHOWCASE_DATASET).first()
    edit = (ContextEdit.objects.filter(dataset__portal=portal, status="kept").order_by("-decided_at").first()
            or ContextEdit.objects.filter(dataset__portal=portal).order_by("-created_at").first())
    top = list(Dataset.objects.filter(portal=portal, usage_count__gt=0).order_by("-usage_count")[:5])
    ctx = {
        "domain": portal.domain, "pages": pages,
        "datasets": nb(Dataset.objects.filter(portal=portal).count()),
        "fields": nb(Field.objects.filter(dataset__portal=portal).count()),
        "cards": nb(Card.objects.filter(dataset__portal=portal).values("dataset").distinct().count()),
        "top": [{"id": d.dataset_id, "title": d.title, "n": nb(d.usage_count),
                 "pct": round(100 * d.usage_count / top[0].usage_count)} for d in top],
        "pair": pair, "bars": bars,
        "tokens": [nb(pair[0].metrics.get("tokens", 0)), nb(pair[1].metrics.get("tokens", 0))] if pair else None,
        "steps": [pair[0].metrics.get("steps_avg"), pair[1].metrics.get("steps_avg")] if pair else None,
        "card": current(ds) if ds else None,
        "edit": edit, "edit_status": STATUS_FR.get(edit.status, edit.status) if edit else "",
        "traps": traps, "stack": stack(),
    }
    (out / "index.html").write_text(render_to_string("ctx/site.html", ctx), encoding="utf-8")
    return pages
