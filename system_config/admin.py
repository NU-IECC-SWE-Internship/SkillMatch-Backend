from django.contrib import admin

from .models import SystemConfig, serialize_value


@admin.register(SystemConfig)
class SystemConfigAdmin(admin.ModelAdmin):
    list_display = ["key", "value", "value_type", "category", "is_public", "default_value", "updated_at", "updated_by"]
    list_editable = ["value"]
    list_filter = ["category", "is_public", "value_type"]
    search_fields = ["key", "description"]
    readonly_fields = ["default_value", "updated_at", "updated_by"]
    fields = ["key", "value", "value_type", "category", "description", "is_public", "default_value", "updated_at", "updated_by"]

    @admin.display(description="Default")
    def default_value(self, obj):
        definition = obj.definition if obj else None
        if definition is None:
            return "-"
        return serialize_value(definition.default, definition.value_type)

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        # Registered keys are referenced by code, so only their value is editable.
        if obj and obj.definition is not None:
            readonly += ["key", "value_type"]
        return readonly

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
