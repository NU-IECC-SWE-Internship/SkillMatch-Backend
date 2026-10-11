from django.apps import AppConfig
from django.db.models.signals import post_delete, post_migrate, post_save


def _sync_after_migrate(sender, **kwargs):
    from .services import sync_registry

    sync_registry()


def _clear_cache(sender, **kwargs):
    from .services import clear_cache

    clear_cache()


class SystemConfigConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "system_config"
    verbose_name = "System configuration"

    def ready(self):
        from .models import SystemConfig

        post_migrate.connect(_sync_after_migrate, sender=self)
        post_save.connect(_clear_cache, sender=SystemConfig)
        post_delete.connect(_clear_cache, sender=SystemConfig)
