from django.urls import path
from . import views

app_name = 'whatsapp'

urlpatterns = [
    # Webhook Meta Cloud API
    path('webhook/', views.WebhookView.as_view(), name='webhook'),

    # Inbox principal
    path('inbox/', views.InboxView.as_view(), name='inbox'),
    path('dashboard/', views.DashboardAgenteView.as_view(), name='dashboard'),
    path('dashboard/supervisor/', views.DashboardSupervisorView.as_view(), name='dashboard_supervisor'),
    path('api/inbox/updates/', views.InboxUpdatesAPIView.as_view(), name='inbox_updates'),
    path('api/inbox/sse/', views.InboxSSEView.as_view(), name='inbox_sse'),
    path('api/mensajes/<int:pk>/marcar-leido/', views.MarcarLeidoView.as_view(), name='marcar_leido'),
    path('api/conversacion/<int:pk>/abrir/', views.AbrirConversacionView.as_view(), name='abrir_conversacion'),
    path('api/mensajes/<int:pk>/', views.ConversacionMessagesAPIView.as_view(), name='mensajes_api'),

    # Conversación
    path('conversacion/nueva/', views.NuevaConversacionView.as_view(), name='nueva_conversacion'),
    path('conversacion/<int:pk>/asignar/', views.AsignarAgenteView.as_view(), name='asignar_agente'),
    path('conversacion/<int:pk>/archivar/', views.ArchivarConversacionView.as_view(), name='archivar'),
    path('conversacion/<int:pk>/desarchivar/', views.DesarchivarConversacionView.as_view(), name='desarchivar'),
    path('conversacion/<int:pk>/bot-toggle/', views.BotToggleView.as_view(), name='bot_toggle'),
    path('conversacion/<int:pk>/enviar-media/', views.EnviarMediaView.as_view(), name='enviar_media'),

    # Plantillas
    path('plantillas/', views.PlantillaListView.as_view(), name='plantilla_list'),
    path('plantillas/nueva/', views.PlantillaCreateView.as_view(), name='plantilla_create'),
    path('plantillas/<int:pk>/editar/', views.PlantillaUpdateView.as_view(), name='plantilla_update'),
    path('plantillas/<int:pk>/eliminar/', views.PlantillaDeleteView.as_view(), name='plantilla_delete'),
    path('plantillas/sincronizar/', views.SyncPlantillasView.as_view(), name='plantilla_sync'),

    # Configuración
    path('config/', views.ConfigView.as_view(), name='config'),
    path('config/estado/', views.ConnectionStatusView.as_view(), name='connection_status'),

    # API externa (para n8n)
    path('api/enviar/', views.APIEnviarMensajeView.as_view(), name='api_enviar'),
    path('api/contacto/', views.APIContactoView.as_view(), name='api_contacto'),
    path('api/handoff/', views.APIHandoffView.as_view(), name='api_handoff'),
    path('api/bot/', views.APIBotToggleExternoView.as_view(), name='api_bot_toggle'),
]
