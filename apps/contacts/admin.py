from django.contrib import admin
from .models import Contacto, CampoPersonalizado, ValorCampo


class ValorCampoInline(admin.TabularInline):
    model = ValorCampo
    extra = 0


@admin.register(Contacto)
class ContactoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'telefono', 'email', 'grupo', 'created_at']
    search_fields = ['nombre', 'telefono', 'email']
    list_filter = ['grupo']
    inlines = [ValorCampoInline]


@admin.register(CampoPersonalizado)
class CampoPersonalizadoAdmin(admin.ModelAdmin):
    list_display = ['etiqueta', 'nombre', 'tipo', 'grupo', 'orden', 'activo']
    list_filter = ['tipo', 'activo', 'grupo']
    list_editable = ['orden', 'activo']
