from django.contrib import admin
from .models import Conversacion, Mensaje, PlantillaHSM, ConfiguracionWhatsApp, LogAPIWhatsApp

@admin.register(ConfiguracionWhatsApp)
class ConfigAdmin(admin.ModelAdmin):
    list_display = ('meta_phone_number_id', 'meta_waba_id', 'updated_at')

@admin.register(Conversacion)
class ConversacionAdmin(admin.ModelAdmin):
    list_display = ('telefono', 'nombre_contacto', 'agente', 'mensajes_no_leidos', 'ventana_activa', 'ultimo_mensaje_at')
    list_filter = ('ventana_activa', 'archivada')
    search_fields = ('telefono', 'nombre_contacto')

@admin.register(Mensaje)
class MensajeAdmin(admin.ModelAdmin):
    list_display = ('conversacion', 'direccion', 'tipo', 'status', 'timestamp')
    list_filter = ('direccion', 'tipo', 'status')

@admin.register(PlantillaHSM)
class PlantillaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'meta_estado', 'meta_categoria', 'activa', 'created_at')
    list_filter = ('meta_estado', 'meta_categoria', 'activa')

@admin.register(LogAPIWhatsApp)
class LogAdmin(admin.ModelAdmin):
    list_display = ('endpoint', 'method', 'response_status', 'exitoso', 'duracion_ms', 'created_at')
    list_filter = ('exitoso',)
