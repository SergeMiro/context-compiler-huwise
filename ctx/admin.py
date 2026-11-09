import difflib

from django.contrib import admin, messages
from django.utils import timezone
from django.utils.html import format_html, mark_safe

from llm import LLMNotConfigured

from .compile import compile_dataset, current, render
from .models import Card, ContextEdit, ToolCall


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ("dataset", "version", "tokens_short", "tokens_full", "created_at")
    search_fields = ("dataset__dataset_id",)
    readonly_fields = [f.name for f in Card._meta.fields]


@admin.register(ContextEdit)
class ContextEditAdmin(admin.ModelAdmin):
    list_display = ("id", "dataset", "kind", "short_after", "source", "status", "result", "created_at")
    list_filter = ("status", "kind", "source")
    search_fields = ("dataset__dataset_id", "after")
    readonly_fields = ("diff", "status", "eval_before", "eval_after", "decided_at", "before")
    fields = ("dataset", "kind", "after", "rationale", "source", "diff", "status", "eval_before", "eval_after", "decided_at")
    autocomplete_fields = ("dataset",)
    actions = ["approve_and_test", "reject"]

    @admin.display(description="edit")
    def short_after(self, obj):
        return obj.after[:80]

    @admin.display(description="eval")
    def result(self, obj):
        a = obj.eval_after or {}
        return f"fixed {len(a.get('fixed', []))} · broken {len(a.get('broken', []))}" if a else "-"

    @admin.display(description="card diff (current → with this edit)")
    def diff(self, obj):
        if not obj.pk:
            return "-"
        now = current(obj.dataset)
        old = now.full if now else ""
        new = render(obj.dataset, extra=obj)[1]
        table = difflib.HtmlDiff(wrapcolumn=70).make_table(old.splitlines(), new.splitlines(), "current", "with edit",
                                                           context=True, numlines=2)
        style = ("<style>.diff td{font:12px monospace;padding:0 4px}.diff_add{background:#d4f8d4}"
                 ".diff_chg{background:#fff3b0}.diff_sub{background:#ffd6d6}</style>")
        return format_html("{}{}", mark_safe(style), mark_safe(table))  # HtmlDiff escapes the card text

    def save_model(self, request, obj, form, change):
        if not change:
            obj.source, obj.before = "human", getattr(current(obj.dataset), "full", "")
        super().save_model(request, obj, form, change)

    @admin.action(description="Approve: test on the golden set, keep only if better")
    def approve_and_test(self, request, queryset):
        from evals.improve import apply_edit
        for e in queryset.filter(status="proposed"):
            if "run" not in e.eval_before:
                self._keep_untested(request, e)
                continue
            try:
                apply_edit(e)
            except LLMNotConfigured:
                self.message_user(request, "No model configured (CTXC_LLM_*): cannot test. Use 'keep without test'.",
                                  messages.ERROR)
                return
            self.message_user(request, f"#{e.id}: {e.status} (fixed {len(e.eval_after['fixed'])}, "
                                       f"broken {len(e.eval_after['broken'])})")

    def _keep_untested(self, request, e):
        from projections.es import upsert_es
        e.status, e.decided_at = "kept", timezone.now()
        e.save(update_fields=["status", "decided_at"])
        compile_dataset(e.dataset)
        upsert_es(e.dataset)
        self.message_user(request, f"#{e.id}: kept (human edit, no eval run attached)", messages.WARNING)

    @admin.action(description="Reject")
    def reject(self, request, queryset):
        n = queryset.filter(status="proposed").update(status="rejected", decided_at=timezone.now())
        self.message_user(request, f"{n} rejected")


@admin.register(ToolCall)
class ToolCallAdmin(admin.ModelAdmin):
    list_display = ("ts", "portal", "tool", "ms", "ok", "error_code")
    list_filter = ("tool", "ok")
