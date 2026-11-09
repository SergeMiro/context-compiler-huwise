from django.test import SimpleTestCase

from tools.odsql import ODSQLRejected, validate

F = {"code_departement", "type_etablissement", "statut_public_prive", "nom_etablissement", "3eme_concours",
     "date_ouverture", "ips", "code academie"}

OK = [
    ({"select": "count(*) as n", "where": "code_departement='021' and type_etablissement='Collège'"}, None),
    ({"select": "type_etablissement, count(*) as n", "group_by": "type_etablissement", "order_by": "n desc"}, None),
    ({"where": "nom_etablissement like 'Lycée%'"}, None),
    ({"where": "code_departement in ('021', '071')"}, None),
    ({"where": "statut_public_prive is not null"}, None),
    ({"where": "date_ouverture >= date'2020-01-01'"}, None),
    ({"select": "avg(ips) as ips_moyen", "where": "code_departement = '021'"}, None),
    ({"where": "nom_etablissement = 'Lycée d\\'Arsonval'"}, None),   # escaped quote inside a string
    ({"where": "nom_etablissement = \"Lycée d'Arsonval\""}, None),  # double-quoted string
    ({"where": "`code academie` = '07'"}, None),                      # backtick-quoted field name
    ({"where": "3eme_concours = 'oui'"}, None),                       # field name starting with a digit
    ({"select": "*", "limit": 5}, None),
    ({"where": "search('lycée agricole')"}, None),
    ({"select": "year(date_ouverture) as y, count(*) as n", "group_by": "year(date_ouverture)"}, None),
]

BAD = [
    ({"where": "code_departemnt='021'"}, "similar fields: code_departement"),
    ({"where": "code_departement='021' or 1=1 --"}, "comments"),
    ({"where": "x /* y */"}, "comments"),
    ({"where": "code_departement='021'; drop"}, "unexpected character ';'"),
    ({"apikey": "abc"}, "parameters not allowed: apikey"),
    ({"where": "secteur = 'public'"}, "unknown field in where: secteur"),
    ({"where": "`not a field` = 1"}, "unknown field"),
    ({"order_by": "n desc"}, "unknown field in order_by: n"),   # alias not defined in select
    ({"where": "a" * 1001}, "longer than"),
    ({"offset": 20000}, "offset"),
    ({"limit": "many"}, "integers"),
    ({"where": "nom_etablissement = 'open"}, "unexpected character"),  # unterminated string
]


class ValidatorTest(SimpleTestCase):
    def test_valid(self):
        for params, _ in OK:
            with self.subTest(params=params):
                out = validate(F, params)
                self.assertLessEqual(out["limit"], 100)

    def test_rejected(self):
        for params, msg in BAD:
            with self.subTest(params=params), self.assertRaisesRegex(ODSQLRejected, msg):
                validate(F, params)

    def test_limits(self):
        self.assertEqual(validate(F, {"limit": 10000})["limit"], 100)
        self.assertEqual(validate(F, {})["limit"], 20)
        self.assertEqual(validate(F, {"limit": 0})["limit"], 0)
