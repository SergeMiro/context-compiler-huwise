from django.core.management.base import BaseCommand

from catalog.models import Portal
from sources.usage import USAGE_DATASET, load_usage


class Command(BaseCommand):
    help = "Load usage signals (agent calls per dataset) from the portal's MCP usage log"

    def add_arguments(self, p):
        p.add_argument("domain")
        p.add_argument("--usage-dataset", default=USAGE_DATASET)

    def handle(self, domain, usage_dataset, **_):
        self.stdout.write(str(load_usage(Portal.objects.get(domain=domain), usage_dataset)))
