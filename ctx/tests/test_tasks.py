from unittest import mock

from django.test import TestCase, override_settings

from catalog.models import Portal
from ctx import tasks
from ctx.locks import portal_lock
from tests.explore_mock import CATALOG, api


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TasksTest(TestCase):
    def setUp(self):
        self.portal = Portal.objects.create(domain="test-tasks.example")

    def test_second_concurrent_scan_is_skipped(self):
        with portal_lock("scan", self.portal.domain) as got:
            self.assertTrue(got)
            self.assertEqual(tasks.scan_portal(self.portal.domain), {"skipped": "locked"})
        with portal_lock("scan", self.portal.domain) as got:  # released after the block
            self.assertTrue(got)

    def test_chain_scan_compile_project(self):
        real_scan = tasks.scan
        with mock.patch.object(tasks, "scan", lambda p, full=False: real_scan(p, full=True, transport=api(CATALOG[:3]))), \
                mock.patch.object(tasks.project_portal, "delay") as project, \
                self.captureOnCommitCallbacks(execute=True):
            stats = tasks.scan_portal(self.portal.domain)
        self.assertEqual(stats["created"], 3)
        project.assert_called_once()
        self.assertEqual(sorted(project.call_args.args[1]), sorted(self.portal.datasets.values_list("dataset_id", flat=True)))

    def test_scan_all_spreads_portals(self):
        Portal.objects.create(domain="other.example")
        with mock.patch.object(tasks.scan_portal, "apply_async") as a:
            tasks.scan_all()
        delays = {c.args[0][0]: c.kwargs["countdown"] for c in a.call_args_list}
        self.assertEqual(set(delays), {"test-tasks.example", "other.example"})
        self.assertTrue(all(0 <= d < 3600 and d % 60 == 0 for d in delays.values()))
