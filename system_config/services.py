import logging
from datetime import timedelta

from django.core.cache import cache
from django.db import DatabaseError

from .registry import REGISTRY

logger = logging.getLogger(__name__)

CACHE_KEY = "system_config:values"
# Other worker processes pick up admin edits within this many seconds.
CACHE_TTL_SECONDS = 60


def _load_overrides() -> dict:
    from .models import SystemConfig

    overrides = {}
    for row in SystemConfig.objects.all():
        try:
            overrides[row.key] = row.typed_value
        except Exception:
            logger.warning("Ignoring invalid config value for %s: %r", row.key, row.value)
    return overrides


def _overrides() -> dict:
    values = cache.get(CACHE_KEY)
    if values is None:
        try:
            values = _load_overrides()
        except DatabaseError:
            # Table not created yet (e.g. before the first migrate).
            return {}
        cache.set(CACHE_KEY, values, CACHE_TTL_SECONDS)
    return values


def clear_cache():
    cache.delete(CACHE_KEY)


def get_config(key: str):
    """Current value for `key`: the DB override if set, otherwise the registry default."""
    overrides = _overrides()
    if key in overrides:
        return overrides[key]
    if key in REGISTRY:
        return REGISTRY[key].default
    raise KeyError(f"Unknown config key '{key}'. Add it to system_config/registry.py.")


def get_hours(key: str) -> timedelta:
    return timedelta(hours=get_config(key))


def get_seconds(key: str) -> timedelta:
    return timedelta(seconds=get_config(key))


def public_config() -> dict:
    from .models import SystemConfig

    public_keys = {d.key for d in REGISTRY.values() if d.is_public}
    try:
        public_keys |= set(
            SystemConfig.objects.filter(is_public=True).values_list("key", flat=True)
        )
        public_keys -= set(
            SystemConfig.objects.filter(is_public=False).values_list("key", flat=True)
        )
    except DatabaseError:
        pass
    return {key: get_config(key) for key in sorted(public_keys)}


def sync_registry() -> int:
    """
    Create a row for every registry key that doesn't have one yet.
    Existing rows are never overwritten so admin edits survive deploys.
    """
    from .models import SystemConfig, serialize_value

    existing = set(SystemConfig.objects.values_list("key", flat=True))
    to_create = [
        SystemConfig(
            key=d.key,
            value=serialize_value(d.default, d.value_type),
            value_type=d.value_type,
            category=d.category,
            description=d.description,
            is_public=d.is_public,
        )
        for d in REGISTRY.values()
        if d.key not in existing
    ]
    SystemConfig.objects.bulk_create(to_create)
    if to_create:
        clear_cache()
    return len(to_create)
