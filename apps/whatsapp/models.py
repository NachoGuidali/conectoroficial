import re

from django.conf import settings
from django.db import models
from django.core.cache import cache


class ConfiguracionWhatsApp(models.Model):
    PROVEEDOR_META = 'meta'
    PROVEEDOR_TWILIO = 'twilio'
    PROVEEDOR_CHOICES = [
        (PROVEEDOR_META, 'Meta Cloud API (oficial)'),
        (PROVEEDOR_TWILIO, 'Twilio'),
    ]

    proveedor = models.CharField(
        max_length=20, choices=PROVEEDOR_CHOICES, default=PROVEEDOR_META,
        help_text='Proveedor de WhatsApp activo. Meta es más barato; Twilio es un intermediario (BSP).',
    )

    # ── Meta Cloud API ──────────────────────────────────────────────────────
    meta_access_token = models.CharField(max_length=600, blank=True, help_text='Token de acceso permanente (System User) de Meta.')
    meta_phone_number_id = models.CharField(max_length=100, blank=True)
    meta_waba_id = models.CharField(max_length=100, blank=True, verbose_name='WhatsApp Business Account ID')
    meta_app_secret = models.CharField(max_length=200, blank=True, help_text='App Secret de la app de Meta, para verificar la firma del webhook.')
    meta_verify_token = models.CharField(max_length=200, blank=True, help_text='Token que se configura en Meta al suscribir el webhook.')
    meta_api_version = models.CharField(max_length=20, default='v21.0')

    # ── Twilio ──────────────────────────────────────────────────────────────
    twilio_account_sid = models.CharField(max_length=100, blank=True, verbose_name='Twilio Account SID')
    twilio_auth_token = models.CharField(max_length=100, blank=True, help_text='Auth Token de Twilio, también valida la firma del webhook.')
    twilio_whatsapp_from = models.CharField(max_length=40, blank=True, help_text='Número de WhatsApp habilitado en Twilio (ej. +14155238886).')

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuración WhatsApp'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete('whatsapp_config')

    @classmethod
    def get_setting(cls, key: str):
        config = cache.get('whatsapp_config')
        if config is None:
            try:
                obj = cls.objects.get(pk=1)
                config = {
                    'proveedor': obj.proveedor,
                    'meta_access_token': obj.meta_access_token,
                    'meta_phone_number_id': obj.meta_phone_number_id,
                    'meta_waba_id': obj.meta_waba_id,
                    'meta_app_secret': obj.meta_app_secret,
                    'meta_verify_token': obj.meta_verify_token,
                    'meta_api_version': obj.meta_api_version,
                    'twilio_account_sid': obj.twilio_account_sid,
                    'twilio_auth_token': obj.twilio_auth_token,
                    'twilio_whatsapp_from': obj.twilio_whatsapp_from,
                }
            except cls.DoesNotExist:
                config = {}
            cache.set('whatsapp_config', config, 300)
        return config.get(key, getattr(settings, key.upper(), ''))


class Conversacion(models.Model):
    ESTADO_BOT = 'bot'
    ESTADO_PENDIENTE = 'pendiente'
    ESTADO_ABIERTA = 'abierta'
    ESTADO_CERRADA = 'cerrada'
    ESTADO_CHOICES = [
        (ESTADO_BOT, 'Bot activo'),
        (ESTADO_PENDIENTE, 'Pendiente de agente'),
        (ESTADO_ABIERTA, 'Abierta'),
        (ESTADO_CERRADA, 'Cerrada'),
    ]

    telefono = models.CharField(max_length=20, unique=True, db_index=True)
    nombre_contacto = models.CharField(max_length=200, blank=True)
    contacto = models.ForeignKey(
        'contacts.Contacto',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='conversaciones',
    )
    agente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='conversaciones',
    )
    estado = models.CharField(
        max_length=20, choices=ESTADO_CHOICES,
        default=ESTADO_ABIERTA, db_index=True,
    )
    ultimo_mensaje_at = models.DateTimeField(null=True, blank=True)
    mensajes_no_leidos = models.PositiveIntegerField(default=0)
    ventana_activa = models.BooleanField(default=False)
    ventana_expira_at = models.DateTimeField(null=True, blank=True)
    bot_crm_activo = models.BooleanField(default=True)
    bot_n8n_activo = models.BooleanField(default=True)
    archivada = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Conversación'
        verbose_name_plural = 'Conversaciones'
        ordering = ['-ultimo_mensaje_at']

    def __str__(self):
        return self.nombre_contacto or self.telefono

    def get_display_name(self):
        if self.contacto_id and self.contacto:
            return self.contacto.nombre
        return self.nombre_contacto or self.telefono


class Mensaje(models.Model):
    TIPO_TEXTO = 'text'
    TIPO_IMAGEN = 'image'
    TIPO_DOCUMENTO = 'document'
    TIPO_AUDIO = 'audio'
    TIPO_VIDEO = 'video'
    TIPO_PLANTILLA = 'template'
    TIPO_INTERACTIVO = 'interactive'
    TIPO_CHOICES = [
        (TIPO_TEXTO, 'Texto'), (TIPO_IMAGEN, 'Imagen'), (TIPO_DOCUMENTO, 'Documento'),
        (TIPO_AUDIO, 'Audio'), (TIPO_VIDEO, 'Video'),
        (TIPO_PLANTILLA, 'Plantilla'), (TIPO_INTERACTIVO, 'Interactivo'),
    ]

    DIR_ENTRANTE = 'in'
    DIR_SALIENTE = 'out'
    DIR_CHOICES = [(DIR_ENTRANTE, 'Entrante'), (DIR_SALIENTE, 'Saliente')]

    STATUS_PENDIENTE = 'pending'
    STATUS_ENVIADO = 'sent'
    STATUS_ENTREGADO = 'delivered'
    STATUS_LEIDO = 'read'
    STATUS_FALLIDO = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDIENTE, 'Pendiente'), (STATUS_ENVIADO, 'Enviado'),
        (STATUS_ENTREGADO, 'Entregado'), (STATUS_LEIDO, 'Leído'), (STATUS_FALLIDO, 'Fallido'),
    ]

    conversacion = models.ForeignKey(Conversacion, on_delete=models.CASCADE, related_name='mensajes')
    whatsapp_message_id = models.CharField(max_length=100, blank=True, db_index=True)
    direccion = models.CharField(max_length=3, choices=DIR_CHOICES)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default=TIPO_TEXTO)
    contenido = models.TextField(blank=True)
    media_url = models.URLField(blank=True, max_length=1000)
    media_id = models.CharField(max_length=100, blank=True)
    media_mime = models.CharField(max_length=100, blank=True)
    media_filename = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDIENTE)
    enviado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    timestamp = models.DateTimeField()
    error_detalle = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Mensaje'
        verbose_name_plural = 'Mensajes'
        ordering = ['timestamp']

    def __str__(self):
        return f'[{self.get_direccion_display()}] {self.conversacion} — {self.timestamp}'


class PlantillaHSM(models.Model):
    CATEGORIA_MARKETING = 'MARKETING'
    CATEGORIA_UTILITY = 'UTILITY'
    CATEGORIA_AUTHENTICATION = 'AUTHENTICATION'
    CATEGORIA_CHOICES = [
        (CATEGORIA_UTILITY, 'Utility'),
        (CATEGORIA_MARKETING, 'Marketing'),
        (CATEGORIA_AUTHENTICATION, 'Authentication'),
    ]

    ESTADO_LOCAL = 'local'
    ESTADO_PENDING = 'PENDING'
    ESTADO_APPROVED = 'APPROVED'
    ESTADO_REJECTED = 'REJECTED'
    ESTADO_CHOICES = [
        (ESTADO_LOCAL, 'No enviada a Meta'),
        (ESTADO_PENDING, 'En revisión'),
        (ESTADO_APPROVED, 'Aprobada'),
        (ESTADO_REJECTED, 'Rechazada'),
    ]

    nombre = models.CharField(max_length=100, unique=True)
    cuerpo = models.TextField(help_text='Usar {{1}}, {{2}}... para variables.')
    variables = models.JSONField(default=list, blank=True)
    activa = models.BooleanField(default=True)
    meta_nombre = models.CharField(max_length=512, blank=True, help_text='Nombre técnico registrado en Meta (snake_case). Si está vacío, se genera del nombre.')
    meta_idioma = models.CharField(max_length=10, default='es_AR')
    meta_categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES, default=CATEGORIA_UTILITY)
    meta_estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default=ESTADO_LOCAL)
    meta_template_id = models.CharField(max_length=100, blank=True)
    meta_rejected_reason = models.TextField(blank=True)
    twilio_content_sid = models.CharField(
        max_length=64, blank=True, verbose_name='Twilio ContentSid',
        help_text='ContentSid de la plantilla creada en la consola de Twilio (empieza con HX).',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Plantilla'
        verbose_name_plural = 'Plantillas'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    def get_meta_nombre(self) -> str:
        if self.meta_nombre:
            return self.meta_nombre
        return re.sub(r'[^a-z0-9_]', '_', self.nombre.strip().lower())

    def preview(self, valores=None):
        text = self.cuerpo
        if valores:
            for i, val in enumerate(valores, start=1):
                text = text.replace(f'{{{{{i}}}}}', str(val))
        return text


class LogAPIWhatsApp(models.Model):
    endpoint = models.CharField(max_length=200)
    method = models.CharField(max_length=10)
    request_body = models.TextField(blank=True)
    response_status = models.IntegerField(null=True)
    response_body = models.TextField(blank=True)
    duracion_ms = models.IntegerField(null=True)
    exitoso = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Log API'
        verbose_name_plural = 'Logs API'
        ordering = ['-created_at']
