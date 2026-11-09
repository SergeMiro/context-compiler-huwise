from django.db import IntegrityError
from django.test import TestCase

from catalog.models import Dataset, Portal


class ModelTest(TestCase):
    def test_dataset_id_unique_per_portal_only(self):
        a, b = Portal.objects.create(domain="a.example"), Portal.objects.create(domain="b.example")
        Dataset.objects.create(portal=a, dataset_id="x", title="X")
        Dataset.objects.create(portal=b, dataset_id="x", title="X")  # same id on another tenant is fine
        with self.assertRaises(IntegrityError):
            Dataset.objects.create(portal=a, dataset_id="x", title="dup")
