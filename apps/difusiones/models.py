from django.conf import settings
from django.db import models


class Difusion(models.Model):
    ESTADO_BORRADOR = 'draft'
    ESTADO_ENVIANDO = 'sending'
    ESTADO_COMPLETADA = 'completed'
    ESTADOS = [
        ('draft', 'Borrador'),
        ('sending', 'Enviando'),
        ('completed', 'Completada'),
    ]

    nombre = models.CharField(max_length=200)
    mensaje = models.TextField(blank=True, help_text='Texto del mensaje. Alternativa: usar plantilla.')
    plantilla = models.ForeignKey(
        'whatsapp.PlantillaHSM',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='difusiones',
    )
    variables_plantilla = models.JSONField(
        default=list, blank=True,
        help_text='Lista de valores para las variables {{1}}, {{2}}... de la plantilla.',
    )
    filtros = models.JSONField(
        default=dict, blank=True,
        help_text='Criterios de filtrado almacenados (fecha, grupo, campos).',
    )
    estado = models.CharField(max_length=20, choices=ESTADOS, default='draft')
    total = models.PositiveIntegerField(default=0)
    enviados = models.PositiveIntegerField(default=0)
    fallidos = models.PositiveIntegerField(default=0)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    enviado_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Difusión'
        verbose_name_plural = 'Difusiones'
        ordering = ['-created_at']

    def __str__(self):
        return self.nombre

    def get_mensaje_texto(self) -> str:
        if self.plantilla:
            return self.plantilla.preview(self.variables_plantilla or None)
        return self.mensaje

    @property
    def pendientes(self):
        return self.total - self.enviados - self.fallidos

    @property
    def porcentaje_enviado(self):
        if not self.total:
            return 0
        return int((self.enviados / self.total) * 100)


class DifusionContacto(models.Model):
    ESTADOS = [
        ('pending', 'Pendiente'),
        ('sent', 'Enviado'),
        ('failed', 'Fallido'),
    ]

    difusion = models.ForeignKey(Difusion, on_delete=models.CASCADE, related_name='destinatarios')
    contacto = models.ForeignKey(
        'contacts.Contacto',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='difusiones_recibidas',
    )
    telefono = models.CharField(max_length=30)
    nombre = models.CharField(max_length=200, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='pending')
    whatsapp_message_id = models.CharField(max_length=100, blank=True)
    enviado_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        unique_together = [('difusion', 'telefono')]
        verbose_name = 'Destinatario'
        verbose_name_plural = 'Destinatarios'
        ordering = ['nombre']

    def __str__(self):
        return f'{self.difusion} → {self.nombre or self.telefono}'
