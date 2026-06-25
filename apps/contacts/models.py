from django.db import models


class CampoPersonalizado(models.Model):
    TIPO_TEXTO = 'text'
    TIPO_NUMERO = 'number'
    TIPO_FECHA = 'date'
    TIPO_BOOLEANO = 'boolean'
    TIPO_EMAIL = 'email'
    TIPO_URL = 'url'
    TIPOS = [
        ('text', 'Texto'), ('number', 'Número'), ('date', 'Fecha'),
        ('boolean', 'Sí/No'), ('email', 'Email'), ('url', 'URL'),
    ]

    nombre = models.CharField(
        max_length=100, unique=True,
        help_text='Identificador interno (sin espacios ni caracteres especiales)',
    )
    etiqueta = models.CharField(max_length=100, help_text='Nombre visible al usuario')
    tipo = models.CharField(max_length=20, choices=TIPOS, default='text')
    grupo = models.CharField(
        max_length=100, blank=True,
        help_text='Vacío = aplica a todos los contactos; con valor = solo a ese grupo',
    )
    orden = models.PositiveSmallIntegerField(default=0)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Campo personalizado'
        verbose_name_plural = 'Campos personalizados'
        ordering = ['orden', 'etiqueta']

    def __str__(self):
        return self.etiqueta

    def get_tipo_display_icon(self):
        icons = {
            'text': 'T', 'number': '#', 'date': '📅',
            'boolean': '✓', 'email': '@', 'url': '🔗',
        }
        return icons.get(self.tipo, 'T')


class Contacto(models.Model):
    nombre = models.CharField(max_length=200)
    telefono = models.CharField(max_length=30, unique=True, db_index=True)
    email = models.EmailField(blank=True)
    grupo = models.CharField(max_length=100, blank=True, db_index=True)
    notas = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Contacto'
        verbose_name_plural = 'Contactos'
        ordering = ['nombre']

    def __str__(self):
        return f'{self.nombre} ({self.telefono})'

    def get_campos_aplicables(self):
        return CampoPersonalizado.objects.filter(
            activo=True,
        ).filter(
            models.Q(grupo='') | models.Q(grupo=self.grupo)
        ).order_by('orden', 'etiqueta')

    def get_campos_con_valores(self):
        campos = self.get_campos_aplicables()
        val_map = {v.campo_id: v.valor for v in self.valores.all()}
        return [(campo, val_map.get(campo.pk, '')) for campo in campos]


class ValorCampo(models.Model):
    contacto = models.ForeignKey(Contacto, on_delete=models.CASCADE, related_name='valores')
    campo = models.ForeignKey(CampoPersonalizado, on_delete=models.CASCADE, related_name='valores')
    valor = models.TextField(blank=True)

    class Meta:
        unique_together = [('contacto', 'campo')]
        verbose_name = 'Valor de campo'
        verbose_name_plural = 'Valores de campos'

    def __str__(self):
        return f'{self.contacto} — {self.campo}: {self.valor}'
