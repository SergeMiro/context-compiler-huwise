"""Which fields join datasets together, and which must never leak sample values."""
import re

# canonical key -> field names seen on Huwise portals (data.education.gouv.fr, 09.11.2026)
KEYS = {
    "uai": {"uai", "identifiant_de_l_etablissement", "numero_uai", "code_uai", "uai_etablissement"},
    "code_commune": {"code_commune", "code_insee_de_la_commune", "commune_code", "code_insee", "code_commune_insee"},
    "code_departement": {"code_departement", "code_du_departement", "departement_code"},
    "code_academie": {"code_academie", "academie_code"},
    "code_region": {"code_region", "code_region_insee", "code_region_2016"},
    "code_region_academique": {"code_region_academique"},
    "code_postal": {"code_postal", "code_postal_uai"},
    "siret": {"siret", "siren_siret"},
    "siren": {"siren"},
}
# Years (annee, rentree_scolaire) are dimensions, not entity keys: joining 96 datasets on "annee" is noise.
_BY_NAME = {name: key for key, names in KEYS.items() for name in names}

PII_TOKENS = {"prenom", "email", "mail", "courriel", "telephone", "tel", "portable", "fax", "naissance", "adresse"}
PII_NAMES = {"nom", "nom_usage", "nom_de_famille", "nom_naissance"}


def key_of(field_name):
    """Canonical join key for a field name, or None."""
    return _BY_NAME.get(field_name.lower())


def is_pii(field_name):
    name = field_name.lower()
    return name in PII_NAMES or bool(PII_TOKENS & set(re.split(r"[_\W]+", name)))
