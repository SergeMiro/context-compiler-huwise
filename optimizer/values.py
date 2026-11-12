"""Value grounding: turn a word from the question ("dijon", "cote d'or") into the exact value stored in a field
('Dijon', "Côte-d'Or") by asking the portal itself. Unresolved or ambiguous -> None: never guess a filter value."""
import functools
import re
import unicodedata

import tools


def norm(text):
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[’'`\-_/]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def literal(value):
    """ODSQL string literal: single quotes, or double quotes when the value holds an apostrophe."""
    return f'"{value}"' if "'" in value else f"'{value}'"


@functools.lru_cache(maxsize=2048)
def candidates(domain, dataset_id, field, text):
    """Distinct values of `field` matching `text` (full-text search), with row counts. One Explore API call."""
    q = norm(text).replace('"', "")
    r = tools._http.get(f"https://{domain}/api/explore/v2.1/catalog/datasets/{dataset_id}/records",
                  params={"select": f"{field}, count(*) as n", "where": f'search({field}, "{q}")',
                          "group_by": field, "limit": 20})
    r.raise_for_status()
    return tuple((row[field], row["n"]) for row in r.json().get("results", []) if row.get(field))


def resolve(domain, dataset_id, field, text):
    """Exact value whose normalised form equals the normalised text, else None."""
    exact = [v for v, _ in candidates(domain, dataset_id, field, text) if norm(v) == norm(text)]
    return exact[0] if len(exact) == 1 else None
