import hashlib
import tempfile
from pathlib import Path

from django.test import TestCase

from catalog.models import Portal
from ctx.compile import compile_portal
from ctx.export import export_llms
from tests.explore_mock import CATALOG, load


def digest(d):
    return {p.relative_to(d).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(d).rglob("*"))
            if p.is_file()}


class ExportTest(TestCase):
    def test_export_is_complete_and_deterministic(self):
        portal = Portal.objects.create(domain="data.education.gouv.fr")
        load(portal, CATALOG[:3])
        compile_portal(portal)
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            self.assertEqual(export_llms(portal, a), 3)
            export_llms(portal, b)
            self.assertEqual(digest(a), digest(b))
            llms = (Path(a) / "llms.txt").read_text()
            self.assertEqual(llms.count("- ["), 3)
            self.assertIn("(datasets/", llms)


class SiteTest(TestCase):
    def test_site_has_index_llms_and_pages(self):
        from ctx.site import build_site
        portal = Portal.objects.create(domain="data.education.gouv.fr")
        load(portal, CATALOG[:3])
        compile_portal(portal)
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(build_site(portal, d), 3)
            index = (Path(d) / "index.html").read_text()
            self.assertIn("data.education.gouv.fr", index)
            self.assertIn("Pas encore d'éval complète", index)  # no runs in the test DB
            self.assertFalse((Path(d) / "eval.json").exists())
            self.assertTrue((Path(d) / "llms.txt").exists())
