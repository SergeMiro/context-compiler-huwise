from django.core.management.base import BaseCommand

from catalog.models import Portal
from ctx.site import build_site


class Command(BaseCommand):
    help = "Static showcase: index.html + llms.txt + datasets/<id>.md"

    def add_arguments(self, p):
        p.add_argument("domain")
        p.add_argument("out_dir")

    def handle(self, domain, out_dir, **_):
        n = build_site(Portal.objects.get(domain=domain), out_dir)
        self.stdout.write(f"index.html + llms.txt + {n} dataset pages in {out_dir}")
