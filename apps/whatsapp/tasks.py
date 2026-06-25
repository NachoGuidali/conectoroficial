import logging
import random
import requests
from datetime import timedelta
from celery import shared_task
from django.db.models import Count, Q
from django.utils import timezone

logger = logging.getLogger('apps.whatsapp')


def auto_asignar_agente(conv) -> bool:
    """
    Asigna la conversación al agente activo con menos conversaciones abiertas.
    Solo considera agentes (rol='agente') activos (is_active=True).
    Retorna True si se asignó, False si no hay agentes disponibles.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    # Agentes activos, en turno, que reciben asignaciones automáticas, con su carga actual
    agentes = (
        User.objects
        .filter(rol=User.ROL_AGENTE, is_active=True, en_turno=True, recibe_asignaciones=True)
        .annotate(carga=Count(
            'conversaciones',
            filter=Q(conversaciones__archivada=False)
        ))
        .order_by('carga', 'pk')
    )

    if not agentes.exists():
        # Fallback: si no hay nadie en turno, intentar con cualquier agente activo que reciba asignaciones
        agentes = (
            User.objects
            .filter(rol=User.ROL_AGENTE, is_active=True, recibe_asignaciones=True)
            .annotate(carga=Count(
                'conversaciones',
                filter=Q(conversaciones__archivada=False)
            ))
            .order_by('carga', 'pk')
        )

    if not agentes.exists():
        logger.warning('Auto-asignación: no hay agentes disponibles para conv %s', conv.pk)
        return False

    agente = agentes.first()
    from .models import Conversacion
    conv.agente = agente
    Conversacion.objects.filter(pk=conv.pk).update(agente=agente)
    logger.info('Conv %s auto-asignada a agente %s (carga: %d)', conv.pk, agente.username, agente.carga)
    return True


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_incoming_message(self, message_data: dict):
    from .models import Conversacion, Mensaje

    phone = message_data.get('from_phone', '')
    if not phone:
        return
    if not phone.startswith('+'):
        phone = '+' + phone

    try:
        # Try to find linked contact
        contacto = None
        try:
            from apps.contacts.models import Contacto
            contacto = Contacto.objects.get(telefono=phone)
        except Exception:
            pass

        contact_name = (contacto.nombre if contacto else None) or message_data.get('contact_name', '')

        conv, created = Conversacion.objects.get_or_create(
            telefono=phone,
            defaults={
                'nombre_contacto': contact_name,
                'contacto': contacto,
            },
        )
        if not created:
            update_fields = []
            if contact_name and not conv.nombre_contacto:
                conv.nombre_contacto = contact_name
                update_fields.append('nombre_contacto')
            if contacto and not conv.contacto_id:
                conv.contacto = contacto
                update_fields.append('contacto')
            if update_fields:
                conv.save(update_fields=update_fields)

        # Auto-asignar si la conversación no tiene agente
        if not conv.agente_id:
            auto_asignar_agente(conv)

        conv.ultimo_mensaje_at = message_data.get('timestamp', timezone.now())
        conv.mensajes_no_leidos = conv.mensajes_no_leidos + 1
        conv.ventana_activa = True
        conv.ventana_expira_at = timezone.now() + timedelta(hours=24)
        # Si estaba archivada y escribe de nuevo, desarchivar automáticamente
        if conv.archivada:
            conv.archivada = False
            logger.info('Conv %s desarchivada automáticamente por nuevo mensaje', conv.pk)
        conv.save()

        msg_type = message_data.get('type', Mensaje.TIPO_TEXTO)
        media_url = message_data.get('media_url', '')
        message_id = message_data.get('message_id', '')

        # Para media recibida, descargar y guardar localmente (evita .enc).
        # El backend (Meta/Twilio) extrae del dict lo que necesita (media_id vs media_url).
        if msg_type in ('image', 'audio', 'video', 'document', 'sticker'):
            from .sender import download_and_save_media
            local_url = download_and_save_media(message_data, conv.pk)
            if local_url:
                media_url = local_url

        Mensaje.objects.create(
            conversacion=conv,
            whatsapp_message_id=message_id,
            direccion=Mensaje.DIR_ENTRANTE,
            tipo=msg_type,
            contenido=message_data.get('content', ''),
            media_url=media_url,
            media_id=message_data.get('media_id', ''),
            media_mime=message_data.get('media_mime', ''),
            media_filename=message_data.get('media_filename', ''),
            status=Mensaje.STATUS_ENTREGADO,
            timestamp=message_data.get('timestamp', timezone.now()),
        )

        # Reenviar a n8n si el bot está activo (con delay random anti-ban)
        if conv.bot_n8n_activo:
            forward_to_n8n_task.apply_async(
                args=[conv.pk, message_data],
                countdown=random.randint(3, 15),
            )

    except Exception as exc:
        logger.exception('Error processing message from %s: %s', phone, exc)
        raise self.retry(exc=exc)


@shared_task
def forward_to_n8n_task(conv_pk: int, message_data: dict):
    from .models import Conversacion
    try:
        conv = Conversacion.objects.get(pk=conv_pk)
    except Conversacion.DoesNotExist:
        return
    _forward_to_n8n(conv, message_data)


def _forward_to_n8n(conv, message_data: dict):
    from django.conf import settings
    n8n_url = getattr(settings, 'N8N_WEBHOOK_URL', '').strip()
    if not n8n_url:
        return
    crm_api_key = getattr(settings, 'CRM_API_KEY', '')
    public_url = getattr(settings, 'PUBLIC_URL', '')
    payload = {
        'event': 'message_received',
        'phone': message_data.get('from_phone', ''),
        'contact_name': conv.nombre_contacto or '',
        'message': message_data.get('content', ''),
        'message_type': message_data.get('type', 'text'),
        'message_id': message_data.get('message_id', ''),
        'conversation_id': conv.pk,
        'timestamp': message_data.get('timestamp', timezone.now()).isoformat()
            if hasattr(message_data.get('timestamp', ''), 'isoformat')
            else str(message_data.get('timestamp', '')),
        # Para que n8n pueda responder de vuelta al CRM:
        'crm_reply_url': f'{public_url}/whatsapp/api/enviar/',
        'crm_api_key': crm_api_key,
    }
    try:
        r = requests.post(n8n_url, json=payload, timeout=10)
        r.raise_for_status()
        logger.info('Mensaje reenviado a n8n para conv %s (status %s)', conv.pk, r.status_code)
    except Exception as e:
        logger.warning('Error reenviando a n8n conv %s: %s', conv.pk, e)


@shared_task
def liberar_asesor_n8n_task(phone: str):
    from django.conf import settings
    url = getattr(settings, 'N8N_LIBERAR_ASESOR_URL', '').strip()
    if not url:
        return
    try:
        r = requests.post(url, json={'phone': phone.lstrip('+')}, timeout=10)
        r.raise_for_status()
        logger.info('Notificado liberar-asesor a n8n para %s (status %s)', phone, r.status_code)
    except Exception as e:
        logger.warning('Error notificando liberar-asesor a n8n para %s: %s', phone, e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_whatsapp_message_task(self, mensaje_id: int):
    from .models import Mensaje
    from .sender import send_text_message
    try:
        msg = Mensaje.objects.select_related('conversacion').get(pk=mensaje_id)
        result = send_text_message(msg.conversacion.telefono, msg.contenido)
        Mensaje.objects.filter(pk=mensaje_id).update(
            whatsapp_message_id=result.get('id', ''),
            status=Mensaje.STATUS_ENVIADO,
        )
    except Exception as exc:
        Mensaje.objects.filter(pk=mensaje_id).update(status=Mensaje.STATUS_FALLIDO, error_detalle=str(exc))
        raise self.retry(exc=exc)


@shared_task
def expire_24h_windows():
    from .models import Conversacion
    updated = Conversacion.objects.filter(
        ventana_activa=True, ventana_expira_at__lt=timezone.now()
    ).update(ventana_activa=False)
    if updated:
        logger.info('Expired %d WhatsApp 24h windows', updated)


def sync_templates_from_meta() -> int:
    """Trae el estado de las plantillas desde Meta y actualiza las locales que matchean
    por (meta_nombre, meta_idioma). Devuelve la cantidad de filas actualizadas."""
    from .models import PlantillaHSM
    from .sender import fetch_templates_from_meta

    actualizadas = 0
    for tpl in fetch_templates_from_meta():
        nombre, idioma = tpl.get('name', ''), tpl.get('language', '')
        if not nombre:
            continue
        body_component = next(
            (c for c in tpl.get('components', []) if c.get('type', '').upper() == 'BODY'), {}
        )
        update_kwargs = {
            'meta_estado': tpl.get('status', PlantillaHSM.ESTADO_PENDING),
            'meta_template_id': tpl.get('id', ''),
            'meta_categoria': tpl.get('category', PlantillaHSM.CATEGORIA_UTILITY),
            'meta_rejected_reason': tpl.get('rejected_reason', '') or '',
        }
        if body_component.get('text'):
            update_kwargs['cuerpo'] = body_component['text']
        actualizadas += PlantillaHSM.objects.filter(meta_nombre=nombre, meta_idioma=idioma).update(**update_kwargs)
    return actualizadas


@shared_task
def sync_templates_from_meta_task():
    actualizadas = sync_templates_from_meta()
    if actualizadas:
        logger.info('Sincronizadas %d plantilla(s) desde Meta', actualizadas)
