from django.test import TestCase

from catalog.models import Dataset, Portal
from ctx.compile import FULL_BUDGET, SHORT_BUDGET, compile_dataset, compile_portal
from ctx.models import ContextEdit
from tests.explore_mock import load


class CompileTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.portal = Portal.objects.create(domain="data.education.gouv.fr")
        load(cls.portal)
        cls.annuaire = Dataset.objects.get(dataset_id="fr-en-annuaire-education")

    def test_all_cards_within_budget_and_deterministic(self):
        stats = compile_portal(self.portal)
        self.assertEqual(stats["unchanged"], 0)
        for ds in Dataset.objects.filter(portal=self.portal):
            card = ds.cards.get()
            self.assertLessEqual(card.tokens_short, SHORT_BUDGET, ds.dataset_id)
            self.assertLessEqual(card.tokens_full, FULL_BUDGET, ds.dataset_id)
        self.assertEqual(compile_portal(self.portal), {"compiled": 0, "unchanged": stats["compiled"]})

    def test_card_shows_key_format_and_cuts_wide_schema(self):
        card = compile_dataset(self.annuaire)
        self.assertIn("code_departement (e.g. '059')", card.short)
        self.assertEqual(self.annuaire.fields.count(), 71)
        self.assertIn("more fields not shown", card.full)

    def test_kept_edits_change_the_card_reverted_do_not(self):
        compile_dataset(self.annuaire)
        ContextEdit.objects.create(dataset=self.annuaire, kind="note", source="human", status="reverted",
                                   after="NOT-IN-CARD")
        self.assertIsNone(compile_dataset(self.annuaire))
        ContextEdit.objects.create(dataset=self.annuaire, kind="note", source="human", status="kept",
                                   after="code_departement has 3 digits: Côte-d'Or = '021'")
        ContextEdit.objects.create(dataset=self.annuaire, kind="synonyms", source="human", status="kept",
                                   after="écoles, collèges, lycées")
        card = compile_dataset(self.annuaire)
        self.assertEqual(card.version, 2)
        self.assertIn("'021'", card.full)
        self.assertIn("Also known as: écoles, collèges, lycées", card.short)
        self.assertNotIn("NOT-IN-CARD", card.full)

    def test_no_pii_samples_in_cards(self):
        self.annuaire.fields.filter(name="mail").update(sample_values=["x@y.fr"])  # even if they got in somehow
        card = compile_dataset(self.annuaire)
        self.assertNotIn("x@y.fr", card.full)
