from django.core.management.base import BaseCommand

from catalog.models import Portal
from evals.golden import load_golden, refresh


class Command(BaseCommand):
    help = "Load golden questions from evals/golden/<name>.json and compute expected answers via the API"

    def add_arguments(self, p):
        p.add_argument("domain")
        p.add_argument("--set", default="education")

    def handle(self, domain, set, **_):
        portal = Portal.objects.get(domain=domain)
        self.stdout.write(f"{load_golden(portal, set)} cases loaded")
        bad = 0
        for slug, value, note in refresh(portal):
            bad += value is None or bool(note)
            self.stdout.write(f"{'!!' if value is None or note else 'ok'} {slug}: {value!r} {note}")
        self.stdout.write(f"{bad} problems")
