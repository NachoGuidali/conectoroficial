from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contacts', '0001_initial'),
        ('whatsapp', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Difusion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=200)),
                ('mensaje', models.TextField(blank=True, help_text='Texto del mensaje. Alternativa: usar plantilla.')),
                ('variables_plantilla', models.JSONField(blank=True, default=list, help_text='Lista de valores para las variables {{1}}, {{2}}... de la plantilla.')),
                ('filtros', models.JSONField(blank=True, default=dict, help_text='Criterios de filtrado almacenados (fecha, grupo, campos).')),
                ('estado', models.CharField(choices=[('draft', 'Borrador'), ('sending', 'Enviando'), ('completed', 'Completada')], default='draft', max_length=20)),
                ('total', models.PositiveIntegerField(default=0)),
                ('enviados', models.PositiveIntegerField(default=0)),
                ('fallidos', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('enviado_at', models.DateTimeField(blank=True, null=True)),
                ('creado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('plantilla', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='difusiones', to='whatsapp.plantillahsm')),
            ],
            options={
                'verbose_name': 'Difusión',
                'verbose_name_plural': 'Difusiones',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='DifusionContacto',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('telefono', models.CharField(max_length=30)),
                ('nombre', models.CharField(blank=True, max_length=200)),
                ('estado', models.CharField(choices=[('pending', 'Pendiente'), ('sent', 'Enviado'), ('failed', 'Fallido')], default='pending', max_length=20)),
                ('whatsapp_message_id', models.CharField(blank=True, max_length=100)),
                ('enviado_at', models.DateTimeField(blank=True, null=True)),
                ('error', models.TextField(blank=True)),
                ('contacto', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='difusiones_recibidas', to='contacts.contacto')),
                ('difusion', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='destinatarios', to='difusiones.difusion')),
            ],
            options={
                'verbose_name': 'Destinatario',
                'verbose_name_plural': 'Destinatarios',
                'ordering': ['nombre'],
                'unique_together': {('difusion', 'telefono')},
            },
        ),
    ]
