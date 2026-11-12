from django.core.management.base import BaseCommand, CommandError

from catalog.models import Portal
from evals.models import EvalRun
from lab import log
from lab.cycle import LabRefused, run_cycle


class Command(BaseCommand):
    help = "AutoContext Lab (preprod only): `lab run <domain>` one cycle; `lab log` print / verify the log"

    def add_arguments(self, p):
        p.add_argument("action", choices=["run", "log"])
        p.add_argument("domain", nargs="?")
        p.add_argument("--base-run", type=int, help="eval run whose dev failures seed the cycle (default: latest)")
        p.add_argument("--max-proposals", type=int)

    def handle(self, action, domain, base_run, max_proposals, **_):
        if action == "log":
            rows = log.read()
            ok, bad = log.verify(rows)
            for r in rows:
                e = r["entry"]
                self.stdout.write(f"{e['ts']} {e['step']:<18} {e.get('decision', '')} {e.get('dataset', '')} "
                                  f"{e.get('gate', e.get('reason', ''))}")
            self.stdout.write(f"{len(rows)} entries, chain {'OK' if ok else f'BROKEN at line {bad}'}")
            return
        if not domain:
            raise CommandError("domain is required")
        portal = Portal.objects.get(domain=domain)
        try:
            rows = run_cycle(portal, EvalRun.objects.get(id=base_run) if base_run else None,
                             max_proposals=max_proposals)
        except LabRefused as e:
            raise CommandError(str(e)) from None
        for r in rows:
            self.stdout.write(str(r["entry"])[:400])
