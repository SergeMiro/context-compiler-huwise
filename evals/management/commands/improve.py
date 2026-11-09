from django.core.management.base import BaseCommand, CommandError

from catalog.models import Portal
from evals.improve import improve
from evals.models import EvalRun
from llm import LLMNotConfigured


class Command(BaseCommand):
    help = "Propose context edits from the last compiled eval run; --mode auto also tests and keeps/reverts them"

    def add_arguments(self, p):
        p.add_argument("domain")
        p.add_argument("--mode", choices=["propose", "auto"], default="propose")
        p.add_argument("--max-edits", type=int, default=10)
        p.add_argument("--run", type=int, help="EvalRun id (default: latest compiled)")

    def handle(self, domain, mode, max_edits, run, **_):
        portal = Portal.objects.get(domain=domain)
        r = EvalRun.objects.get(id=run) if run else None
        try:
            s = improve(portal, mode=mode, run=r, max_edits=max_edits)
        except LLMNotConfigured as e:
            raise CommandError(f"no model configured: {e}") from None
        except EvalRun.DoesNotExist:
            raise CommandError("no finished compiled eval run: run manage.py eval first") from None
        self.stdout.write(f"proposed {s['proposed']} · kept {s['kept']} · reverted {s['reverted']} · "
                          f"correct answers {s['correct_before']} -> {s['correct_after']} of {s['of']}")
        if mode == "propose":
            self.stdout.write("review and approve in /admin/ctx/contextedit/")
