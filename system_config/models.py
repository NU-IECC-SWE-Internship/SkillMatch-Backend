import json

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .registry import BOOL, FLOAT, INT, JSON, REGISTRY, STR, VALUE_TYPES


TRUE_VALUES = {"true", "1", "yes", "on"}
FALSE_VALUES = {"false", "0", "no", "off"}


def parse_value(raw: str, value_type: str):
    """Convert the stored text into a Python value. Raises ValueError if invalid."""
    text = (raw or "").strip()
    if value_type == INT:
        return int(text)
    if value_type == FLOAT:
        return float(text)
    if value_type == BOOL:
        lowered = text.lower()
        if lowered in TRUE_VALUES:
            return True
        if lowered in FALSE_VALUES:
            return False
        raise ValueError(f"'{raw}' is not a valid true/false value.")
    if value_type == JSON:
        return json.loads(text)
    if value_type == STR:
        return raw or ""
    raise ValueError(f"Unknown value type '{value_type}'.")


def serialize_value(value, value_type: str) -> str:
    if value_type == JSON:
        return json.dumps(value)
    if value_type == BOOL:
        return "true" if value else "false"
    return str(value)


class SystemConfig(models.Model):
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField(blank=True)
    value_type = models.CharField(max_length=10, choices=VALUE_TYPES, default=STR)
    category = models.CharField(max_length=50, blank=True, db_index=True)
    description = models.TextField(blank=True)
    is_public = models.BooleanField(default=False)

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["category", "key"]
        verbose_name = "System config"
        verbose_name_plural = "System config"

    def __str__(self):
        return f"{self.key} = {self.value}"

    @property
    def typed_value(self):
        return parse_value(self.value, self.value_type)

    @property
    def definition(self):
        return REGISTRY.get(self.key)

    def clean(self):
        try:
            parsed = self.typed_value
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ValidationError({"value": f"Invalid {self.get_value_type_display()}: {exc}"})

        definition = self.definition
        if definition is None or self.value_type not in (INT, FLOAT):
            return
        if definition.min_value is not None and parsed < definition.min_value:
            raise ValidationError({"value": f"Must be at least {definition.min_value}."})
        if definition.max_value is not None and parsed > definition.max_value:
            raise ValidationError({"value": f"Must be at most {definition.max_value}."})
