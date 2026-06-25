from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0002_user_en_turno'),
    ]
    operations = [
        migrations.AddField(
            model_name='user',
            name='recibe_asignaciones',
            field=models.BooleanField(default=True, verbose_name='Recibe asignaciones automáticas'),
        ),
    ]
