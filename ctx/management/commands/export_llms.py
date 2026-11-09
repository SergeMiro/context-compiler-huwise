from django.core.management.base import BaseCommand

from catalog.models import Portal
from ctx.export import export_llms


class Command(BaseCommand):
    help = "Write llms.txt and datasets/<id>.md for a portal"

    def add_arguments(self, p):
        p.add_argument("domain")
        p.add_argument("out_dir")

    def handle(self, domain, out_dir, **_):
        n = export_llms(Portal.objects.get(domain=domain), out_dir)
        self.stdout.write(f"{n} dataset pages + llms.txt in {out_dir}")
