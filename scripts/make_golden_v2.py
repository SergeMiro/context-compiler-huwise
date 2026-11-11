"""Generate evals/golden/education_v2.json: ~100 questions across shapes the legacy 30 do not cover well.
Reference ODSQL is written per template with its own field choice (codes, not the labels the recipe resolves),
expected values come from the API via `golden_refresh --set education_v2`. Splits by slug hash: 40 % dev,
30 % val, 30 % holdout. Run: python3 scripts/make_golden_v2.py"""
import hashlib
import json
from pathlib import Path

D = "fr-en-annuaire-education"
TYPES = {"Collège": ("collèges", "middle schools"), "Lycée": ("lycées", "high schools"), "Ecole": ("écoles", "primary schools")}
COMMUNES = ["Dijon", "Lyon", "Angers", "Toulouse", "Nantes", "Lille", "Rennes", "Strasbourg", "Bordeaux", "Nice",
            "Montpellier", "Saint-Etienne", "Besançon", "Grenoble", "Reims", "Le Havre"]
DEPTS = {"Côte-d'Or": "021", "Nord": "059", "Rhône": "069", "Gironde": "033", "Bouches-du-Rhône": "013",
         "Finistère": "029", "Haute-Garonne": "031", "Bas-Rhin": "067", "Hérault": "034", "Loire-Atlantique": "044",
         "Isère": "038", "Doubs": "025"}
ACADS = ["Dijon", "Lyon", "Bordeaux", "Rennes", "Lille", "Toulouse", "Grenoble", "Nantes", "Strasbourg", "Besançon"]
REGIONS = ["Bretagne", "Normandie", "Occitanie", "Grand Est", "Hauts-de-France", "Nouvelle-Aquitaine",
           "Pays de la Loire", "Bourgogne-Franche-Comté"]
STAT = {"Public": "publics", "Privé": "privés"}
rows = []


def add(slug, question, where=None, tags=(), dataset=D, odsql=None, answer="total_count", tolerance=0.05):
    rows.append({"slug": slug, "question": question, "datasets": [dataset] if dataset else [],
                 "odsql": odsql if odsql is not None else ({"where": where} if where else {}),
                 "answer": answer, "tolerance": tolerance, "tags": list(tags)})


def q(v):
    return f'"{v}"' if "'" in v else f"'{v}'"


types = list(TYPES)
for i, c in enumerate(COMMUNES):  # commune x type, two phrasings
    t = types[i % 3]
    phr = [f"Combien y a-t-il de {TYPES[t][0]} à {c} ?", f"Combien de {TYPES[t][0]} à {c} ?"][i % 2]
    add(f"v2-{t[:3].lower()}-{c.lower().replace(' ', '-')}", phr,
        f"nom_commune={q(c)} and type_etablissement={q(t)}", ["count", "commune"])
for i, (name, code) in enumerate(DEPTS.items()):  # department x type x status, reference by code (3 digits)
    t, s = types[i % 3], list(STAT)[i % 2]
    add(f"v2-dep-{code}-{t[:3].lower()}-{s[:3].lower()}", f"Combien de {TYPES[t][0]} {STAT[s]} en {name} ?" if i % 2 == 0
        else f"Combien de {TYPES[t][0]} {STAT[s]} dans le département {name} ?",
        f"code_departement='{code}' and type_etablissement={q(t)} and statut_public_prive={q(s)}",
        ["count", "department", "code-format"])
for i, a in enumerate(ACADS):
    t = types[i % 3]
    add(f"v2-acad-{a.lower()}-{t[:3].lower()}", f"Combien de {TYPES[t][0]} dans l'académie de {a} ?",
        f"libelle_academie={q(a)} and type_etablissement={q(t)}", ["count", "academie"])
for i, r in enumerate(REGIONS):
    t = types[i % 3]
    add(f"v2-reg-{i}-{t[:3].lower()}", f"Combien de {TYPES[t][0]} en {r} ?",
        f"libelle_region={q(r)} and type_etablissement={q(t)}", ["count", "region"])
for t in types:
    add(f"v2-fr-{t[:3].lower()}", f"Combien de {TYPES[t][0]} en France ?", f"type_etablissement={q(t)}", ["count", "national"])
for i, c in enumerate(["Lyon", "Paris", "Toulouse", "Nantes", "Lille", "Bordeaux", "Brest", "Rennes"]):
    t = types[i % 3]
    add(f"v2-en-{c.lower()}-{t[:3].lower()}", f"How many {TYPES[t][1]} are there in {c}?",
        f"nom_commune={q(c)} and type_etablissement={q(t)}", ["count", "commune", "english"])
extra = [  # a condition the recipe does not cover -> agent path
    ("segpa", "ont une SEGPA", "segpa='1'", "Collège"), ("ulis", "ont un dispositif ULIS", "ulis='1'", "Collège"),
    ("internat", "proposent un internat", "hebergement='1'", "Lycée"),
    ("restauration", "ont une restauration scolaire", "restauration='1'", "Collège")]
for i, (name, code) in enumerate(list(DEPTS.items())[:8]):
    key, phrase, cond, t = extra[i % 4]
    add(f"v2-x-{key}-{code}", f"Combien de {TYPES[t][0]} en {name} {phrase} ?",
        f"code_departement='{code}' and type_etablissement={q(t)} and {cond}", ["count", "filter", "extra-condition"])
for code, name in [("021", "Côte-d'Or"), ("059", "Nord"), ("013", "Bouches-du-Rhône")]:
    add(f"v2-rep-{code}", f"Combien d'établissements classés REP+ en {name} ?",
        f"code_departement='{code}' and appartenance_education_prioritaire='REP+'", ["count", "filter"])
for r in ["Occitanie", "Bretagne", "Grand Est"]:  # trap: a separate dataset, not type_etablissement='Lycée'
    add(f"v2-lm-{r.lower().replace(' ', '-')}", f"Combien de lycées des métiers en {r} ?", dataset="fr-en-lycees-metiers",
        where=f"libelle_region={q(r)}", tags=["count", "trap", "dataset-choice"])
IPS = "fr-en-ips-colleges-ap2023"
for code, name in [("21", "Côte-d'Or"), ("59", "Nord"), ("69", "Rhône"), ("33", "Gironde"), ("13", "Bouches-du-Rhône"), ("29", "Finistère")]:
    add(f"v2-ips-{code}", f"Quel est l'IPS moyen des collèges du département {name} à la rentrée 2025-2026 ?", dataset=IPS,
        odsql={"select": "avg(ips) as v", "where": f"code_du_departement='{code}' and rentree_scolaire='2025-2026'"},
        answer="field:v", tolerance=0.01, tags=["aggregate", "code-format"])
BAC = "fr-en-baccalaureat-par-academie"
for a in ["LYON", "BORDEAUX", "RENNES", "LILLE", "TOULOUSE", "NANTES"]:
    add(f"v2-bac-{a.lower()}", f"Combien de candidats ont été admis au bac général dans l'académie de {a.title()} en 2025 ?",
        dataset=BAC, odsql={"select": "sum(nombre_d_admis_totaux) as v",
                            "where": f"academie='{a}' and year(session)=2025 and voie='BAC GENERAL'"},
        answer="field:v", tolerance=0.01, tags=["aggregate", "date-year"])
for t, s in [("Collège", "Public"), ("Lycée", "Privé"), ("Ecole", "Privé")]:
    add(f"v2-grp-acad-{t[:3].lower()}-{s[:3].lower()}", f"Quelle académie compte le plus de {TYPES[t][0]} {STAT[s]} ?",
        odsql={"select": "libelle_academie, count(*) as n", "where": f"type_etablissement={q(t)} and statut_public_prive={q(s)}",
               "group_by": "libelle_academie", "order_by": "n desc", "limit": 1},
        answer="field:libelle_academie", tags=["text", "group"])
add("v2-grp-dep-lyc", "Quel département compte le plus de lycées ?",
    odsql={"select": "libelle_departement, count(*) as n", "where": "type_etablissement='Lycée'",
           "group_by": "libelle_departement", "order_by": "n desc", "limit": 1}, answer="field:libelle_departement",
    tags=["text", "group"])
for slug, question in [("hopitaux-dijon", "Combien d'hôpitaux y a-t-il à Dijon ?"),
                       ("prix-immo-lyon", "Quel est le prix moyen du mètre carré à Lyon ?"),
                       ("meteo-nantes", "Quelle température fera-t-il demain à Nantes ?"),
                       ("pharmacies-nord", "Combien de pharmacies dans le Nord ?"),
                       ("chomage-bfc", "Quel est le taux de chômage en Bourgogne-Franche-Comté ?"),
                       ("gares-rennes", "Combien de gares SNCF à Rennes ?")]:
    add(f"v2-nodata-{slug}", question, dataset=None, tags=["no-data"])
add("v2-amb-guadeloupe", "Combien de lycées en Guadeloupe ?", "libelle_region='Guadeloupe' and type_etablissement='Lycée'",
    ["count", "ambiguous-place"])
add("v2-amb-paris-col", "Combien de collèges à Paris ?", "nom_commune='Paris' and type_etablissement='Collège'",
    ["count", "ambiguous-place"])

for r in rows:
    h = int(hashlib.sha256(r["slug"].encode()).hexdigest(), 16) % 10
    r["split"] = "dev" if h < 4 else "val" if h < 7 else "holdout"
out = Path(__file__).resolve().parent.parent / "evals" / "golden" / "education_v2.json"
out.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n")
print(len(rows), {s: sum(r["split"] == s for r in rows) for s in ("dev", "val", "holdout")})
