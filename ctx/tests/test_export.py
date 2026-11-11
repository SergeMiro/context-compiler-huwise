import json
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
    def test_site_has_both_languages_data_and_pages(self):
        from ctx.site import build_site
        portal = Portal.objects.create(domain="data.education.gouv.fr")
        load(portal, CATALOG[:3])
        compile_portal(portal)
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(build_site(portal, d), 3)
            index = (Path(d) / "index.html").read_text()
            self.assertIn("Nous ne remplaçons pas Huwise", index)
            self.assertIn("Run A/B/C en cours.", index)  # no runs in the test DB
            self.assertIn("We do not replace Huwise", (Path(d) / "en" / "index.html").read_text())
            arch = json.loads((Path(d) / "data" / "architecture.json").read_text())
            statuses = {n["status"] for n in arch["nodes"]}
            self.assertLessEqual(statuses, {"VERIFIED", "INFERRED", "PROPOSED"})
            # every Huwise block marked VERIFIED carries at least one source; ours are all PROPOSED
            for n in arch["nodes"]:
                self.assertTrue(n["layer"] == "ours" and n["status"] == "PROPOSED" or n["layer"] == "huwise")
                if n["status"] == "VERIFIED":
                    self.assertTrue(n["sources"], n["id"])
            self.assertTrue((Path(d) / "llms.txt").exists())


class StatsTest(TestCase):
    def test_mcnemar_and_bootstrap(self):
        from ctx.site import boot_ci, mcnemar
        x, y = [0] * 10 + [1] * 10, [1] * 10 + [1] * 10
        self.assertLess(mcnemar(x, y), 0.01)  # 10 discordant pairs, all one way
        self.assertEqual(mcnemar(x, x), 1.0)
        lo, hi = boot_ci(x, y)
        self.assertTrue(0 < lo <= 50 <= hi)
