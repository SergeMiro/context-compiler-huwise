from django.core.management.base import BaseCommand, CommandError

from llm import LLMNotConfigured

from catalog.models import Portal
from evals.runner import run_eval, table


class Command(BaseCommand):
    help = "Run the golden questions through the agent: naked (generic tools) vs compiled (cards)"

    def add_arguments(self, p):
        p.add_argument("domain")
        p.add_argument("--mode", choices=["huwise", "naked", "compiled", "optimized", "both", "abc"], default="both",
                       help="both = naked+compiled; abc = naked (A) + compiled (B) + optimized (C), same cases; huwise = the real Huwise MCP (needs HUWISE_API_KEY)")
        p.add_argument("--cases", default="", help="comma-separated slugs")
        p.add_argument("--suite", default="education", help="golden file name")
        p.add_argument("--split", default="", help="dev | val | holdout (default: all cases)")

    def handle(self, domain, mode, cases, suite, split, **_):
        portal = Portal.objects.get(domain=domain)
        slugs = [s for s in cases.split(",") if s] or None
        modes = {"both": ["naked", "compiled"], "abc": ["naked", "compiled", "optimized"]}.get(mode, [mode])
        try:
            runs = [run_eval(portal, m, slugs=slugs, suite=suite, split=split or None) for m in modes]
        except LLMNotConfigured as e:
            raise CommandError(f"no model configured: {e}") from None
        self.stdout.write(table(runs))
        for r in runs:
            failed = [s for s, v in r.metrics["per_case"].items() if not v["answer_ok"]]
            self.stdout.write(f"{r.mode} run #{r.id} failed: {', '.join(failed) or '-'}")
