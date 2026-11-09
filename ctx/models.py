from django.db import models

from catalog.models import Dataset, Portal


class Card(models.Model):
    """Compiled context for one dataset. Versioned: rollback = previous version."""
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="cards")
    version = models.PositiveIntegerField()
    short = models.TextField()
    full = models.TextField()
    tokens_short = models.PositiveIntegerField()
    tokens_full = models.PositiveIntegerField()
    content_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["dataset", "version"], name="uniq_card_version")]
        ordering = ["dataset", "-version"]


class ContextEdit(models.Model):
    KINDS = [(k, k) for k in ("description", "synonyms", "query_template", "note")]
    STATUSES = [(s, s) for s in ("proposed", "kept", "reverted", "rejected")]
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="edits")
    kind = models.CharField(max_length=20, choices=KINDS)
    before = models.TextField(blank=True)
    after = models.TextField()
    source = models.CharField(max_length=10, choices=[("llm", "llm"), ("human", "human")])
    status = models.CharField(max_length=10, choices=STATUSES, default="proposed", db_index=True)
    eval_before = models.JSONField(default=dict)
    eval_after = models.JSONField(default=dict)
    rationale = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)


class ToolCall(models.Model):
    """Observability of the hot path. Never stores the question, the query or the API key."""
    portal = models.ForeignKey(Portal, on_delete=models.CASCADE)
    tool = models.CharField(max_length=40)
    ms = models.PositiveIntegerField()
    ok = models.BooleanField()
    error_code = models.CharField(max_length=60, blank=True)
    ts = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["portal", "ts"])]
