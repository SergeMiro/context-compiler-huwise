from django.core.management.base import BaseCommand

from catalog.models import Portal


class Command(BaseCommand):
    help = "Project the current cards of a portal into Elasticsearch and Neo4j"

    def add_arguments(self, p):
        p.add_argument("domain")
        p.add_argument("--rebuild-index", action="store_true", help="new ES index for all portals (mapping change)")

    def handle(self, domain, rebuild_index, **_):
        import time

        from projections import es, graph
        portal = Portal.objects.get(domain=domain)
        t = time.monotonic()
        n = es.rebuild_index(Portal.objects.all())[0] if rebuild_index else es.project_es(portal)
        self.stdout.write(f"es: {n} cards in {time.monotonic() - t:.1f}s")
        t = time.monotonic()
        self.stdout.write(f"neo4j: {graph.project_graph(portal)} in {time.monotonic() - t:.1f}s")
