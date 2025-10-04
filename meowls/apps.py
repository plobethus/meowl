from django.apps import AppConfig


class MeowlsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "meowls"

    # Keep ready() empty to avoid circular imports / missing models
    def ready(self):
        # If you later add signals, import them here (e.g., from . import signals)
        pass
