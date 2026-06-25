from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('whatsapp', '0002_conversacion_contacto'),
    ]
    operations = [
        migrations.AddField(
            model_name='mensaje',
            name='media_mime',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='mensaje',
            name='media_filename',
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
