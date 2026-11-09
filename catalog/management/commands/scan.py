from django.core.management.base import BaseCommand

from catalog.models import Portal
from sources.explore import scan


class Command(BaseCommand):
    help = "Scan a Huwise/Opendatasoft portal catalog (full or incremental by `modified`)"

    def add_arguments(self, p):
        p.add_argument("domain")
        p.add_argument("--full", action="store_true")
        p.add_argument("--no-samples", action="store_true")

    def handle(self, domain, full, no_samples, **_):
        portal, _ = Portal.objects.get_or_create(domain=domain)
        self.stdout.write(str(scan(portal, full=full, samples=not no_samples)))
