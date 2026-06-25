from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='CampoPersonalizado',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(help_text='Identificador interno (sin espacios ni caracteres especiales)', max_length=100, unique=True)),
                ('etiqueta', models.CharField(help_text='Nombre visible al usuario', max_length=100)),
                ('tipo', models.CharField(choices=[('text', 'Texto'), ('number', 'Número'), ('date', 'Fecha'), ('boolean', 'Sí/No'), ('email', 'Email'), ('url', 'URL')], default='text', max_length=20)),
                ('grupo', models.CharField(blank=True, help_text='Vacío = aplica a todos los contactos; con valor = solo a ese grupo', max_length=100)),
                ('orden', models.PositiveSmallIntegerField(default=0)),
                ('activo', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Campo personalizado',
                'verbose_name_plural': 'Campos personalizados',
                'ordering': ['orden', 'etiqueta'],
            },
        ),
        migrations.CreateModel(
            name='Contacto',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=200)),
                ('telefono', models.CharField(db_index=True, max_length=30, unique=True)),
                ('email', models.EmailField(blank=True)),
                ('grupo', models.CharField(blank=True, db_index=True, max_length=100)),
                ('notas', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Contacto',
                'verbose_name_plural': 'Contactos',
                'ordering': ['nombre'],
            },
        ),
        migrations.CreateModel(
            name='ValorCampo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('valor', models.TextField(blank=True)),
                ('contacto', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='valores', to='contacts.contacto')),
                ('campo', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='valores', to='contacts.campopersonalizado')),
            ],
            options={
                'verbose_name': 'Valor de campo',
                'verbose_name_plural': 'Valores de campos',
                'unique_together': {('contacto', 'campo')},
            },
        ),
    ]
