from django.db import models


class Portal(models.Model):
    """A Huwise / Opendatasoft portal = one tenant. Everything below belongs to exactly one portal."""
    domain = models.CharField(max_length=255, unique=True)
    title = models.CharField(max_length=300, blank=True)
    scan_cursor = models.DateTimeField(null=True, blank=True)  # max `modified` seen by the last scan
    llm_budget_per_day = models.PositiveIntegerField(default=50)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.domain


class Dataset(models.Model):
    portal = models.ForeignKey(Portal, on_delete=models.CASCADE, related_name="datasets")
    dataset_id = models.CharField(max_length=255)
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)  # plain text, HTML stripped
    themes = models.JSONField(default=list)
    keywords = models.JSONField(default=list)
    license = models.CharField(max_length=300, blank=True)
    publisher = models.CharField(max_length=300, blank=True)
    update_frequency = models.CharField(max_length=50, blank=True)
    records_count = models.BigIntegerField(default=0)
    modified = models.DateTimeField(null=True)
    federated = models.BooleanField(default=False)
    source_domain = models.CharField(max_length=255, blank=True)
    source_dataset = models.CharField(max_length=255, blank=True)
    raw_metas = models.JSONField(default=dict)
    # lineage entered by hand; DERIVED_FROM edges in Neo4j are projected from here
    sources = models.ManyToManyField("self", through="Transformation", symmetrical=False,
                                     through_fields=("target", "source"), related_name="derived")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["portal", "dataset_id"], name="uniq_portal_dataset")]
        indexes = [models.Index(fields=["portal", "modified"])]

    def __str__(self):
        return self.dataset_id


class Field(models.Model):
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="fields")
    position = models.PositiveIntegerField(default=0)
    name = models.CharField(max_length=255)
    label = models.CharField(max_length=500, blank=True)
    type = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    sample_values = models.JSONField(default=list)  # <= 10 most frequent values, never for PII fields
    is_key = models.BooleanField(default=False)
    is_pii = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["dataset", "name"], name="uniq_dataset_field")]
        ordering = ["dataset", "position"]

    def __str__(self):
        return self.name


class Transformation(models.Model):
    source = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="+")
    target = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="+")
    kind = models.CharField(max_length=30)  # filter, join, aggregate...

    class Meta:
        constraints = [models.UniqueConstraint(fields=["source", "target"], name="uniq_edge")]
