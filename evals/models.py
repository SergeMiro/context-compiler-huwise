from django.db import models

from catalog.models import Portal


class EvalCase(models.Model):
    portal = models.ForeignKey(Portal, on_delete=models.CASCADE, related_name="eval_cases")
    slug = models.SlugField(max_length=100)
    question = models.TextField()
    expected_dataset = models.CharField(max_length=255, blank=True)  # blank = "no data on this portal"
    reference_odsql = models.JSONField(default=dict)  # {select, where, group_by}
    expected_value = models.JSONField(null=True)  # filled by golden_refresh, never by hand
    tolerance = models.FloatField(default=0.05)
    tags = models.JSONField(default=list)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["portal", "slug"], name="uniq_case")]


class EvalRun(models.Model):
    portal = models.ForeignKey(Portal, on_delete=models.CASCADE)
    mode = models.CharField(max_length=10, choices=[("naked", "naked"), ("compiled", "compiled")])
    model = models.CharField(max_length=200)
    card_versions = models.JSONField(default=dict)
    metrics = models.JSONField(default=dict)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True)


class EvalResult(models.Model):
    run = models.ForeignKey(EvalRun, on_delete=models.CASCADE, related_name="results")
    case = models.ForeignKey(EvalCase, on_delete=models.CASCADE)
    found_dataset = models.CharField(max_length=255, blank=True)
    odsql_valid_first_try = models.BooleanField(default=False)
    answer = models.TextField(blank=True)
    answer_ok = models.BooleanField(default=False)
    steps = models.PositiveIntegerField(default=0)
    ms = models.PositiveIntegerField(default=0)
    tokens = models.PositiveIntegerField(default=0)
    transcript = models.JSONField(default=list)
