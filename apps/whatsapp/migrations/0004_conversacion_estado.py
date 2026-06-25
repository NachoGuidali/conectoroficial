from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('whatsapp', '0003_mensaje_media_fields'),
    ]
    operations = [
        migrations.AddField(
            model_name='conversacion',
            name='estado',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('bot', 'Bot activo'),
                    ('pendiente', 'Pendiente de agente'),
                    ('abierta', 'Abierta'),
                    ('cerrada', 'Cerrada'),
                ],
                default='abierta',
                db_index=True,
            ),
        ),
    ]
