"""Demo scenarios for the showcase. RECORDED ones are real runs (model + Explore API) saved by
`manage.py record_traces`; SIMULATED ones change one input on purpose (a renamed field, a new data version, a 403)
and run the real optimizer code against that fixture. The page shows which is which."""

SCENARIOS = [
    {"id": "dijon", "kind": "recorded", "question": "Combien y a-t-il de collèges à Dijon ?",
     "title": {"fr": "Le cas principal", "en": "The main case"},
     "ref": {"dataset": "fr-en-annuaire-education", "where": "nom_commune='Dijon' and type_etablissement='Collège'"}},
    {"id": "code-format", "kind": "recorded", "question": "Combien de collèges publics y a-t-il en Côte-d'Or ?",
     "title": {"fr": "Code département : '21' ou '021' ?", "en": "Department code: '21' or '021'?"},
     "ref": {"dataset": "fr-en-annuaire-education",
             "where": "code_departement='021' and type_etablissement='Collège' and statut_public_prive='Public'"}},
    {"id": "trap-dataset", "kind": "recorded", "question": "Combien de lycées des métiers en Bourgogne-Franche-Comté ?",
     "title": {"fr": "Le mauvais jeu de données", "en": "The wrong dataset"},
     "ref": {"dataset": "fr-en-lycees-metiers", "where": "libelle_region='Bourgogne-Franche-Comté'"}},
    {"id": "aggregate", "kind": "recorded",
     "question": "Quel est l'IPS moyen des collèges de Côte-d'Or à la rentrée 2025-2026 ?",
     "title": {"fr": "Une moyenne (agrégation)", "en": "An average (aggregation)"},
     "ref": {"dataset": "fr-en-ips-colleges-ap2023", "select": "avg(ips) as v",
             "where": "code_du_departement='21' and rentree_scolaire='2025-2026'", "answer": "v"}},
    {"id": "ambiguous", "kind": "recorded", "question": "Combien de lycées en Guadeloupe ?",
     "title": {"fr": "Lieu ambigu (département = région)", "en": "Ambiguous place (department = region)"},
     "ref": {"dataset": "fr-en-annuaire-education",
             "where": "libelle_region='Guadeloupe' and type_etablissement='Lycée'"}},
    {"id": "drift", "kind": "simulated", "question": "Combien y a-t-il de collèges à Dijon ?",
     "title": {"fr": "Le schéma a changé", "en": "The schema changed"},
     "fixture": "the field nom_commune changes type in the local catalog copy (never on the portal)"},
    {"id": "stale-cache", "kind": "simulated", "question": "Combien y a-t-il de collèges à Dijon ?",
     "title": {"fr": "Cache périmé", "en": "Stale cache"},
     "fixture": "the dataset gets a new data_processed date in the local catalog copy"},
    {"id": "forbidden", "kind": "simulated", "question": "Combien y a-t-il de collèges à Dijon ?",
     "title": {"fr": "Jeu de données non autorisé", "en": "Dataset not allowed"},
     "fixture": "the Explore API answers 403 (mock transport), as for a restricted dataset without the right key"},
]
BY_ID = {s["id"]: s for s in SCENARIOS}
