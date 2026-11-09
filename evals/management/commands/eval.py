from django.core.management.base import BaseCommand, CommandError

from llm import LLMNotConfigured

from catalog.models import Portal
from evals.runner import run_eval, table


class Command(BaseCommand):
    help = "Run the golden questions through the agent: naked (generic tools) vs compiled (cards)"

    def add_arguments(self, p):
        p.add_argument("domain")
        p.add_argument("--mode", choices=["naked", "compiled", "both"], default="both")
        p.add_argument("--cases", default="", help="comma-separated slugs")

    def handle(self, domain, mode, cases, **_):
        portal = Portal.objects.get(domain=domain)
        slugs = [s for s in cases.split(",") if s] or None
        try:
            runs = [run_eval(portal, m, slugs=slugs) for m in (["naked", "compiled"] if mode == "both" else [mode])]
        except LLMNotConfigured as e:
            raise CommandError(f"no model configured: {e}") from None
        self.stdout.write(table(runs))
        for r in runs:
            failed = [s for s, v in r.metrics["per_case"].items() if not v["answer_ok"]]
            self.stdout.write(f"{r.mode} run #{r.id} failed: {', '.join(failed) or '-'}")
