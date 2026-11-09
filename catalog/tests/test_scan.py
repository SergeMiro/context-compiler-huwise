import copy
from datetime import timedelta

import httpx
from django.test import TestCase

from catalog.models import Dataset, Field, Portal
from sources.explore import html_to_text, scan
from sources.keys import is_pii, key_of
from tests.explore_mock import CATALOG, FACETS, HEADERS, api

class ScanTest(TestCase):
    def setUp(self):
        self.portal = Portal.objects.create(domain="data.education.gouv.fr")

    def test_full_scan_creates_datasets_fields_and_samples(self):
        stats = scan(self.portal, full=True, transport=api(CATALOG))
        self.assertEqual(stats["created"], len(CATALOG))
        self.assertEqual(Field.objects.count(), sum(len(d["fields"]) for d in CATALOG))
        ds = Dataset.objects.get(dataset_id="fr-en-annuaire-education")
        self.assertNotIn("<p>", ds.description)
        dep = ds.fields.get(name="code_departement")
        self.assertTrue(dep.is_key)
        self.assertEqual(dep.sample_values[0], "059")  # 3-digit codes: exactly what an agent must know
        self.assertEqual(ds.fields.get(name="statut_public_prive").sample_values, ["Public", "Privé"])

    def test_pii_fields_get_no_samples(self):
        facets = copy.deepcopy(FACETS)
        facets["facets"].append({"name": "mail", "facets": [{"value": "x@y.fr", "count": 1}]})
        FACETS_BAK = FACETS["facets"]
        FACETS["facets"] = facets["facets"]
        try:
            scan(self.portal, full=True, transport=api(CATALOG))
        finally:
            FACETS["facets"] = FACETS_BAK
        mail = Field.objects.get(dataset__dataset_id="fr-en-annuaire-education", name="mail")
        self.assertTrue(mail.is_pii)
        self.assertEqual(mail.sample_values, [])

    def test_incremental_touches_only_changed_and_full_deletes_gone(self):
        scan(self.portal, full=True, samples=False, transport=api(CATALOG))
        self.portal.refresh_from_db()
        cursor = self.portal.scan_cursor
        later = copy.deepcopy(CATALOG[:2])
        later[0]["metas"]["default"]["modified"] = (cursor + timedelta(hours=1)).isoformat()
        later[0]["metas"]["default"]["title"] = "Renamed"
        stats = scan(self.portal, samples=False, transport=api(later))  # 2nd item is not newer than cursor
        self.assertEqual((stats["mode"], stats["updated"], stats["created"]), ("incremental", 1, 0))
        self.assertEqual(Dataset.objects.get(dataset_id=later[0]["dataset_id"]).title, "Renamed")
        stats = scan(self.portal, full=True, samples=False, transport=api(CATALOG[1:]))
        self.assertEqual(Dataset.objects.count(), len(CATALOG) - 1)

    def test_cursor_does_not_move_on_error(self):
        with self.assertRaises(httpx.HTTPStatusError):
            scan(self.portal, full=True, transport=api(CATALOG, fail_on="/facets"))
        self.portal.refresh_from_db()
        self.assertIsNone(self.portal.scan_cursor)

    def test_helpers(self):
        self.assertEqual(html_to_text("<p>a&nbsp;<b>b</b></p><p>c</p>"), "a b c")
        self.assertEqual(key_of("identifiant_de_l_etablissement"), "uai")
        self.assertIsNone(key_of("annee"))
        self.assertTrue(is_pii("telephone") and is_pii("adresse_1") and is_pii("nom"))
        self.assertFalse(is_pii("nom_etablissement") or is_pii("nom_commune") or is_pii("code_postal"))


class ScanErrorsTest(TestCase):
    def test_4xx_on_one_dataset_facets_is_skipped(self):
        portal = Portal.objects.create(domain="p.example")

        def handler(request):
            if request.url.path.endswith("/facets"):
                return httpx.Response(400, json={"error_key": "NoDomainMatchingException"})
            return httpx.Response(200, json=CATALOG, headers=HEADERS)
        stats = scan(portal, full=True, transport=httpx.MockTransport(handler))
        self.assertGreater(stats["samples_failed"], 0)
        portal.refresh_from_db()
        self.assertIsNotNone(portal.scan_cursor)
