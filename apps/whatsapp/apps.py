from django.apps import AppConfig


class WhatsappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.whatsapp'
    verbose_name = 'WhatsApp'

    def ready(self):
        from django.db.models.signals import post_migrate
        post_migrate.connect(_setup_periodic_tasks, sender=self)


def _setup_periodic_tasks(sender, **kwargs):
    try:
        from django_celery_beat.models import PeriodicTask, IntervalSchedule
        schedule_1h, _ = IntervalSchedule.objects.get_or_create(every=1, period=IntervalSchedule.HOURS)
        PeriodicTask.objects.get_or_create(
            name='expire_24h_windows',
            defaults={'task': 'apps.whatsapp.tasks.expire_24h_windows', 'interval': schedule_1h, 'enabled': True},
        )
        PeriodicTask.objects.get_or_create(
            name='sync_templates_from_meta',
            defaults={'task': 'apps.whatsapp.tasks.sync_templates_from_meta_task', 'interval': schedule_1h, 'enabled': True},
        )
    except Exception:
        pass
