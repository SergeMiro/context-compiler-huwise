from django.contrib import admin
from django.utils.html import format_html_join

from .models import EvalCase, EvalResult, EvalRun


@admin.register(EvalCase)
class EvalCaseAdmin(admin.ModelAdmin):
    list_display = ("slug", "question", "expected_value", "tags")
    search_fields = ("slug", "question")


class ResultInline(admin.TabularInline):
    model = EvalResult
    fields = ("case", "answer_ok", "found_dataset", "odsql_valid_first_try", "steps", "ms", "answer")
    readonly_fields = fields
    extra = 0
    can_delete = False


@admin.register(EvalRun)
class EvalRunAdmin(admin.ModelAdmin):
    list_display = ("id", "mode", "model", "answer_ok", "dataset_ok", "started_at")
    list_filter = ("mode", "model")
    readonly_fields = ("portal", "mode", "model", "metrics_table", "started_at", "finished_at")
    exclude = ("metrics", "card_versions")
    inlines = [ResultInline]

    def answer_ok(self, obj):
        return obj.metrics.get("answer_ok")

    def dataset_ok(self, obj):
        return obj.metrics.get("dataset_ok")

    def metrics_table(self, obj):
        rows = [(k, v) for k, v in obj.metrics.items() if k not in ("per_case", "by_tag")]
        rows += [(f"tag {t}", v) for t, v in obj.metrics.get("by_tag", {}).items()]
        return format_html_join("", "<div><b>{}</b>: {}</div>", rows)
