import random

import httpx
from django.test import TestCase, override_settings

import tools
from catalog.models import Dataset, Field, Portal
from llm import FakeLLM
from optimizer import cache, evidence, pipeline, recipes, router
from optimizer.values import candidates
from tests.explore_mock import load
from tools.odsql import ODSQLRejected, validate

D = "data.education.gouv.fr"


def api(handler_rows):
    """Explore API mock: value lookups (group_by) answer from handler_rows[field], counts answer 23."""
    seen = []

    def handler(request):
        p = dict(request.url.params)
        seen.append(p)
        if "group_by" in p:
            return httpx.Response(200, json={"results": handler_rows.get(p["group_by"], [])})
        if "DIJON" in p.get("where", "") or "'21'" in p.get("where", ""):
            return httpx.Response(200, json={"total_count": 0, "results": []})
        return httpx.Response(200, json={"total_count": 23, "results": []})
    return httpx.Client(transport=httpx.MockTransport(handler)), seen


ROWS = {"nom_commune": [{"nom_commune": "Dijon", "n": 148}, {"nom_commune": "Fontaine-lès-Dijon", "n": 7}],
        "libelle_departement": [{"libelle_departement": "Côte-d'Or", "n": 665}],
        "libelle_region": [], "type_etablissement": [{"type_etablissement": "Collège", "n": 9180}]}


class ParseTest(TestCase):
    def test_shapes(self):
        p = recipes.parse("Combien y a-t-il de collèges à Dijon ?")
        self.assertEqual((p["type"], p["status"], p["place_text"], p["place_fields"]), ("Collège", None, "dijon", ("nom_commune",)))
        p = recipes.parse("Combien de lycées privés dans l'académie de Dijon ?")
        self.assertEqual((p["type"], p["status"], p["place_fields"]), ("Lycée", "Privé", ("libelle_academie",)))
        self.assertEqual(recipes.parse("How many middle schools are there in Lyon?")["place_text"], "lyon")
        self.assertIsNone(recipes.parse("Combien d'écoles compte la France ?")["place_text"])

    def test_rejects_what_it_does_not_cover(self):
        for q in ["Combien de lycées des métiers en Bretagne ?",  # another dataset
                  "Combien de lycées proposent un internat en Bretagne ?",  # extra condition
                  "Combien d'élèves dans les collèges de Paris ?",  # not a count of establishments
                  "Combien de collèges et lycées en Côte-d'Or ?",  # two types
                  "Quel est l'IPS moyen des collèges ?"]:  # not a count
            self.assertIn("reject", recipes.parse(q), q)


@override_settings(ES_INDEX="test-cards")
class RecipeTest(TestCase):
    def setUp(self):
        self.portal = Portal.objects.create(domain=D)
        load(self.portal)
        self.http, self.seen = api(ROWS)
        self._http, tools._http = tools._http, self.http
        candidates.cache_clear()
        cache.CACHE.items.clear()
        ds = Dataset.objects.get(portal=self.portal, dataset_id=recipes.DIRECTORY)
        self._verified = dict(recipes.VERIFIED_SCHEMA)
        recipes.VERIFIED_SCHEMA[recipes.DIRECTORY] = recipes.schema_hash(ds)

    def tearDown(self):
        tools._http = self._http
        recipes.VERIFIED_SCHEMA.update(self._verified)

    def test_fast_route_answers_without_a_model(self):
        boom = FakeLLM([])
        r = pipeline.answer(D, "Combien y a-t-il de collèges à Dijon ?", chat=boom)
        self.assertEqual(r["route"], "FAST")
        self.assertEqual(boom.calls, [])
        self.assertIn("23", r["answer"])
        self.assertEqual(r["evidence"]["status"], "verified")
        self.assertEqual(r["queries"][0]["params"]["where"], "type_etablissement='Collège' and nom_commune='Dijon'")

    def test_unresolved_place_goes_to_the_agent(self):
        r = router.route(D, "Combien de collèges à Dijonville ?")
        self.assertEqual(r["route"], "STANDARD")
        self.assertIn("not found", r["reasons"][0])

    def test_schema_drift_disables_the_recipe(self):
        ds = Dataset.objects.get(portal=self.portal, dataset_id=recipes.DIRECTORY)
        Field.objects.filter(dataset=ds, name="nom_commune").update(type="int")
        r = router.route(D, "Combien y a-t-il de collèges à Dijon ?")
        self.assertEqual(r["route"], "STANDARD")
        self.assertIn("schema drift", r["reasons"][0])

    def test_value_hints_on_empty_result(self):
        r = pipeline.grounded_query(D, recipes.DIRECTORY, {"where": "nom_commune='DIJON'", "limit": 0})
        self.assertEqual(r["hint"], ["nom_commune: 'DIJON' is stored as 'Dijon'"])
        ds = Dataset.objects.get(portal=self.portal, dataset_id=recipes.DIRECTORY)
        Field.objects.filter(dataset=ds, name="code_departement").update(sample_values=["021", "059"])
        r = pipeline.grounded_query(D, recipes.DIRECTORY, {"where": "code_departement='21'", "limit": 0})
        self.assertIn("try '021'", r["hint"][0])

    def test_unknown_field_is_refused_before_the_api(self):
        n = len(self.seen)
        r = pipeline.grounded_query(D, recipes.DIRECTORY, {"where": "commune='Dijon'", "limit": 0})
        self.assertIn("unknown field", r["error"])
        self.assertEqual(len(self.seen), n)

    def test_unbacked_number_is_not_stated(self):
        chat = FakeLLM([[("find_dataset", {"question": "x"})], "Il y a 4 200 lycées des métiers."])
        r = pipeline.answer(D, "Combien de lycées des métiers en Bretagne ?", chat=chat)
        self.assertEqual(r["route"], "STANDARD")
        self.assertEqual(r["evidence"]["status"], "blocked")
        self.assertTrue(r["answer"].startswith("Je ne peux pas"))


class CacheTest(TestCase):
    def setUp(self):
        self.portal = Portal.objects.create(domain=D)
        load(self.portal)
        self.ds = Dataset.objects.get(portal=self.portal, dataset_id=recipes.DIRECTORY)

    def test_key_changes_with_scope_schema_and_data_version(self):
        params = {"where": "x='1'", "limit": 0}
        base = cache.key(D, "public", self.ds, params)
        self.assertEqual(base, cache.key(D, "public", self.ds, dict(params)))
        self.assertNotEqual(base, cache.key(D, cache.scope_of("secret-key"), self.ds, params))
        self.assertNotEqual(base, cache.key("other.portal", "public", self.ds, params))
        self.ds.raw_metas = {"data_processed": "2026-12-01T00:00:00"}
        self.ds.save()
        changed_data = cache.key(D, "public", self.ds, params)
        self.assertNotEqual(base, changed_data)
        Field.objects.create(dataset=self.ds, name="new_column", type="text", position=999)
        self.assertNotEqual(changed_data, cache.key(D, "public", self.ds, params))

    @override_settings(SECRET_KEY="k")
    def test_scope_never_contains_the_key(self):
        s = cache.scope_of("my-api-key-123")
        self.assertNotIn("my-api-key-123", s)
        self.assertEqual(cache.scope_of(None), "public")

    def test_ttl(self):
        now = [0.0]
        c = cache.Cache(ttl=10, clock=lambda: now[0])
        c.put("a", {"v": 1})
        self.assertEqual(c.get("a"), {"v": 1})
        now[0] = 11
        self.assertIsNone(c.get("a"))
        self.assertEqual(c.stats()["hits"], 1)


class EvidenceTest(TestCase):
    def test_statuses(self):
        evidence._demo()
        q = [{"dataset_id": "d", "params": {}, "ok": True, "result": {"total_count": 0, "results": []}}]
        self.assertEqual(evidence.check("Combien ?", "Il y a 0 collège.", q)["status"], "partially_verified")
        q = [{"dataset_id": "d", "params": {}, "ok": True, "result": {"total_count": 1, "results": [{"v": 105.879}]}}]
        self.assertEqual(evidence.check("IPS moyen ?", "L'IPS moyen est de 105,9.", q)["status"], "verified")
        self.assertEqual(evidence.check("Combien ?", "pas de données", [])["status"], "unverified")
        q = [{"dataset_id": "d", "params": {}, "ok": True, "result": {"total_count": 1, "results": [{"a": "Versailles"}]}}]
        self.assertEqual(evidence.check("Quelle académie ?", "C'est Versailles.", q)["status"], "verified")


class ValidatorPropertyTest(TestCase):
    """Property-style checks with a fixed seed (no extra dependency): whatever an agent writes, an unknown
    identifier, a comment or an extra parameter never reaches the API."""
    FIELDS = {"nom_commune", "type_etablissement", "code_departement", "ips"}

    def test_random_unknown_identifiers_are_rejected(self):
        rnd = random.Random(7)
        for _ in range(300):
            name = rnd.choice("abcdefghxyz_") + "".join(rnd.choice("abcdefghijklmnopqrstuvwxyz_0123456789")
                                                        for _ in range(rnd.randint(1, 12)))
            if name in self.FIELDS or name.lower() in ("and", "or", "not", "in", "like", "is", "null", "as", "asc",
                                                       "desc", "true", "false", "distinct", "between", "date",
                                                       "datetime", "time", "geom"):
                continue
            with self.assertRaises(ODSQLRejected):
                validate(self.FIELDS, {"where": f"{name} = 'x'"})

    def test_generated_valid_queries_pass_and_injections_fail(self):
        rnd = random.Random(11)
        for _ in range(200):
            f = rnd.choice(sorted(self.FIELDS))
            v = rnd.choice(["'Dijon'", "'021'", "80", '"COTE D\'OR"'])
            out = validate(self.FIELDS, {"where": f"{f} = {v}", "limit": rnd.randint(0, 500)})
            self.assertLessEqual(out["limit"], 100)
        for bad in ["nom_commune='a' -- x", "ips /* x */ = 1", "nom_commune='a'; drop"]:
            with self.assertRaises(ODSQLRejected):
                validate(self.FIELDS, {"where": bad})
        with self.assertRaises(ODSQLRejected):
            validate(self.FIELDS, {"where": "ips=1", "apikey": "x"})
