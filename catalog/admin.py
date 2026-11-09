from django.contrib import admin

from .models import Dataset, Field, Portal


@admin.register(Portal)
class PortalAdmin(admin.ModelAdmin):
    list_display = ("domain", "scan_cursor", "llm_budget_per_day")


class FieldInline(admin.TabularInline):
    model = Field
    fields = ("name", "type", "label", "is_key", "is_pii", "sample_values")
    readonly_fields = fields
    extra = 0
    can_delete = False


@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    list_display = ("dataset_id", "title", "records_count", "usage_count", "modified")
    list_filter = ("portal",)
    search_fields = ("dataset_id", "title")
    ordering = ("-usage_count",)
    readonly_fields = ("card",)
    exclude = ("raw_metas", "sources")
    inlines = [FieldInline]

    @admin.display(description="current card")
    def card(self, obj):
        from django.utils.html import format_html

        from ctx.compile import current
        c = current(obj)
        return format_html("<pre style='white-space:pre-wrap'>v{} · {} / {} tokens\n\n{}\n\n{}</pre>", c.version,
                           c.tokens_short, c.tokens_full, c.short, c.full) if c else "-"
