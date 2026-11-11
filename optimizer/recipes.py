"""Verified query recipes: parameterised ODSQL for the most common question shape on the directory dataset
("how many <type> [public|private] in <place>"). A recipe is used only when every word of the question is
understood, every slot resolves to an exact stored value, and the dataset schema still has the hash the recipe was
verified against. Anything else returns None with a reason, and the router falls back to the agent."""
import hashlib
import re

from catalog.models import Dataset

from .values import literal, norm, resolve

RECIPES_VERSION = "2026-11-11.1"
DIRECTORY = "fr-en-annuaire-education"
# fields the recipe reads; the schema hash covers only these, so unrelated schema changes do not disable it
RECIPE_FIELDS = ("type_etablissement", "statut_public_prive", "nom_commune", "libelle_departement",
                 "libelle_academie", "libelle_region")

TYPES = [  # (regex on the normalised question, stored value)
    (r"\b(colleges?|middle schools?)\b", "Collège"),
    (r"\b(lycees?|high schools?)\b", "Lycée"),
    (r"\b(ecoles?|primary schools?)\b", "Ecole"),
]
STATUS = [(r"\b(publics?|publiques?|public schools?)\b", "Public"), (r"\b(prives?|privees?|private)\b", "Privé")]
PLACE_CUES = [  # (regex: everything before the LAST cue, then the place; fields to try in order)
    (r"^(?P<pre>.*?)\b(?:de |dans |in )?l ?academie (?:de |d )?(?P<p>.+)$", ("libelle_academie",)),
    (r"^(?P<pre>.*?)\b(?:en |dans |in )?(?:la )?region (?P<p>.+)$", ("libelle_region",)),
    (r"^(?P<pre>.*?)\b(?:dans le |du |in )?departement (?:de |du |des |d )?(?P<p>.+)$", ("libelle_departement",)),
    (r"^(?P<pre>.*)\b(?:a|in) (?P<p>.+)$", ("nom_commune",)),
    (r"^(?P<pre>.*)\b(?:en|dans le|dans la|dans les|du|des) (?P<p>.+)$", ("libelle_departement", "libelle_region")),
]
PHRASES = r"\b(y a t il|il y a|compte t on|are there|is there|y en a t il)\b"
NATIONAL = r"\b(en france|in france|la france|france entiere)\b"
COUNT = r"^(combien|how many|nombre)\b"
# words allowed to be left over once intent, type, status and place are taken out; any other word (internat,
# segpa, ips, eleves, 2025, metiers...) means the question asks for more than the recipe does -> no recipe
FILLER = set("combien de d y a t il en compte compte-t-on on how many are there is the of nombre total au aux le la "
             "les l des du dans etablissements etablissement ? sont existe existent there's".split())


def schema_hash(ds, fields=RECIPE_FIELDS):
    rows = sorted((f.name, f.type) for f in ds.fields.filter(name__in=fields))
    return hashlib.sha256(repr(rows).encode()).hexdigest()[:16]


def _strip(text, pattern):
    return re.sub(pattern, " ", text).strip()


def parse(question):
    """Question -> {"type", "status", "place_text", "place_fields"} or {"reject": reason}. Pure, no I/O."""
    q = _strip(norm(question).rstrip(" ?"), PHRASES)
    if not re.search(COUNT, q):
        return {"reject": "not a count question"}
    types = [v for rx, v in TYPES if re.search(rx, q)]
    if len(types) != 1:
        return {"reject": "establishment type missing or ambiguous"}
    rest = q
    for rx, _ in TYPES:
        rest = _strip(rest, rx)
    status = [v for rx, v in STATUS if re.search(rx, rest)]
    if len(status) > 1:
        return {"reject": "public and private both asked"}
    for rx, _ in STATUS:
        rest = _strip(rest, rx)
    out = {"type": types[0], "status": status[0] if status else None, "place_text": None, "place_fields": ()}
    if re.search(NATIONAL, rest):
        rest = _strip(rest, NATIONAL)
    else:
        for rx, fields in PLACE_CUES:
            m = re.search(rx, rest)
            if m:
                out["place_text"], out["place_fields"] = m.group("p").strip(), fields
                rest = m.group("pre")
                break
    left = [w for w in rest.split() if w not in FILLER]
    if left:
        return {"reject": f"words the recipe does not cover: {' '.join(left)}"}
    return out


def plan(domain, question):
    """-> {"recipe", "dataset_id", "params", "slots", "schema_hash", "calls"} or {"reject": reason}. Resolves
    the place against the portal (1-2 API calls) and checks the schema hash."""
    p = parse(question)
    if "reject" in p:
        return p
    ds = Dataset.objects.filter(portal__domain=domain, dataset_id=DIRECTORY).first()
    if ds is None:
        return {"reject": f"{DIRECTORY} not in the catalog"}
    h = schema_hash(ds)
    if h != VERIFIED_SCHEMA.get(DIRECTORY):
        return {"reject": f"schema drift on {DIRECTORY}: recipe verified on {VERIFIED_SCHEMA.get(DIRECTORY)}, now {h}"}
    where = [f"type_etablissement={literal(p['type'])}"]
    slots, calls = {"type_etablissement": p["type"]}, []
    if p["status"]:
        where.append(f"statut_public_prive={literal(p['status'])}")
        slots["statut_public_prive"] = p["status"]
    if p["place_text"]:
        hits = []
        for field in p["place_fields"]:
            calls.append({"tool": "resolve_value", "field": field, "text": p["place_text"]})
            value = resolve(domain, DIRECTORY, field, p["place_text"])
            if value:
                hits.append((field, value))
        if len(hits) != 1:
            return {"reject": f"place '{p['place_text']}' " + ("not found" if not hits else "ambiguous: " +
                                                                ", ".join(f"{f}={v}" for f, v in hits)),
                    "calls": calls}
        field, value = hits[0]
        where.append(f"{field}={literal(value)}")
        slots[field] = value
    return {"recipe": f"count_establishments@{RECIPES_VERSION}", "dataset_id": DIRECTORY,
            "params": {"where": " and ".join(where), "limit": 0}, "slots": slots, "schema_hash": h, "calls": calls}


# schema hashes the recipes were verified against (manage.py recipes --verify writes nothing; a human updates this
# after checking the new schema, so a silent column rename can never keep a recipe alive)
VERIFIED_SCHEMA = {DIRECTORY: "ceae47849fae998c"}  # 11.11.2026, fields + types of RECIPE_FIELDS
