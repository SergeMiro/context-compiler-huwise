import random
import statistics
import time

from django.core.management.base import BaseCommand

import tools
from catalog.models import Dataset

QUESTIONS = ["collèges publics", "IPS des lycées", "effectifs CPGE", "résultats du brevet", "écoles maternelles",
             "taux de réussite au bac", "élèves en situation de handicap", "lycées professionnels", "internat",
             "carte scolaire"]


class Command(BaseCommand):
    help = "Latency of find_dataset / explain_dataset (p50/p95), in process"

    def add_arguments(self, p):
        p.add_argument("domain")
        p.add_argument("-n", type=int, default=200)

    def handle(self, domain, n, **_):
        ids = list(Dataset.objects.filter(portal__domain=domain).values_list("dataset_id", flat=True))
        random.seed(0)
        tools.find_dataset(domain, "warm up")
        for name, call in (("find_dataset", lambda: tools.find_dataset(domain, random.choice(QUESTIONS))),
                           ("explain_dataset", lambda: tools.explain_dataset(domain, random.choice(ids)))):
            ms = []
            for _ in range(n):
                t = time.monotonic()
                call()
                ms.append((time.monotonic() - t) * 1000)
            q = statistics.quantiles(ms, n=20)
            self.stdout.write(f"{name}: n={n} p50={statistics.median(ms):.1f} ms p95={q[18]:.1f} ms")
