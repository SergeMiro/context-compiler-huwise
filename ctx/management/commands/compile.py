from django.core.management.base import BaseCommand
from django.db.models import Max

from catalog.models import Portal
from ctx.compile import compile_portal
from ctx.models import Card


class Command(BaseCommand):
    help = "Compile context cards for every dataset of a portal"

    def add_arguments(self, p):
        p.add_argument("domain")

    def handle(self, domain, **_):
        portal = Portal.objects.get(domain=domain)
        stats = compile_portal(portal)
        stats.update(Card.objects.filter(dataset__portal=portal).aggregate(
            max_tokens_short=Max("tokens_short"), max_tokens_full=Max("tokens_full")))
        self.stdout.write(str(stats))
