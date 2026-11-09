from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from catalog.models import Portal
from ctx.compile import compile_portal, current
from ctx.models import ContextEdit
from projections import es
from tests.explore_mock import load


@override_settings(ES_INDEX="test-cards")
class AdminTest(TestCase):
    def setUp(self):
        es.drop_index()
        self.portal = Portal.objects.create(domain="data.education.gouv.fr")
        load(self.portal)
        compile_portal(self.portal)
        self.ds = self.portal.datasets.get(dataset_id="fr-en-annuaire-education")
        self.client.force_login(User.objects.create_superuser("admin", "a@example.com", "x"))

    def tearDown(self):
        es.drop_index()

    def test_diff_page_and_human_keep(self):
        e = ContextEdit.objects.create(dataset=self.ds, kind="note", after="code_departement = '021' for Côte-d'Or",
                                       source="human", before=current(self.ds).full)
        page = self.client.get(f"/admin/ctx/contextedit/{e.id}/change/").content.decode()
        self.assertIn("diff_add", page)
        self.assertIn("code_departement = &#x27;021&#x27;", page)
        r = self.client.post("/admin/ctx/contextedit/", {"action": "approve_and_test", "_selected_action": [e.id]})
        self.assertEqual(r.status_code, 302)
        e.refresh_from_db()
        self.assertEqual(e.status, "kept")
        self.assertIn("'021' for Côte-d'Or", current(self.ds).full)

    def test_reject_and_pages_render(self):
        e = ContextEdit.objects.create(dataset=self.ds, kind="synonyms", after="bahut", source="llm")
        self.client.post("/admin/ctx/contextedit/", {"action": "reject", "_selected_action": [e.id]})
        e.refresh_from_db()
        self.assertEqual(e.status, "rejected")
        for url in ("/admin/catalog/dataset/", f"/admin/catalog/dataset/{self.ds.id}/change/", "/admin/evals/evalrun/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
