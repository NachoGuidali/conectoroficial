import logging
import random
import time

from celery import shared_task
from django.db.models import F
from django.utils import timezone

logger = logging.getLogger('apps.whatsapp')

LOCK_TTL = 7200  # 2 horas máximo por difusión


def _personalizar(mensaje: str, dc) -> str:
    """Sustituye {variables} en el mensaje con datos del contacto."""
    if '{' not in mensaje:
        return mensaje

    contacto = dc.contacto
    # Siempre incluir el snapshot como fallback
    vals = {
        'nombre': dc.nombre or '',
        'telefono': dc.telefono or '',
        'email': '',
        'grupo': '',
    }

    if contacto:
        vals.update({
            'nombre': contacto.nombre or dc.nombre or '',
            'telefono': contacto.telefono or dc.telefono or '',
            'email': contacto.email or '',
            'grupo': contacto.grupo or '',
        })
        # Campos personalizados — iterar objetos con prefetch
        try:
            for vc in contacto.valores.select_related('campo').all():
                if vc.campo_id and vc.campo:
                    vals[vc.campo.nombre] = vc.valor or ''
        except Exception as e:
            logger.warning('Error cargando campos personalizados para %s: %s', dc.telefono, e)

    result = mensaje
    for key, value in vals.items():
        result = result.replace(f'{{{key}}}', value)

    if result != mensaje:
        logger.info('Variables sustituidas para %s: %s → %s', dc.telefono, list(vals.keys()), result[:80])

    return result


def _lock_key(difusion_id):
    return f'difusion_lock_{difusion_id}'


def _acquire_lock(cache, difusion_id):
    from django.core.cache import cache as django_cache
    c = cache or django_cache
    return c.add(_lock_key(difusion_id), '1', LOCK_TTL)


def _release_lock(difusion_id):
    from django.core.cache import cache
    cache.delete(_lock_key(difusion_id))


@shared_task(bind=True, max_retries=0)
def send_difusion_task(self, difusion_id: int):
    from django.core.cache import cache
    from .models import Difusion, DifusionContacto
    from apps.whatsapp.sender import send_text_message, send_template_message
    from apps.whatsapp.models import Conversacion, PlantillaHSM

    try:
        difusion = Difusion.objects.get(pk=difusion_id)
    except Difusion.DoesNotExist:
        logger.error('Difusion %s not found', difusion_id)
        return

    estados_validos = (Difusion.ESTADO_BORRADOR, Difusion.ESTADO_ENVIANDO)
    if difusion.estado not in estados_validos:
        logger.warning('Difusion %s already in state %s, skipping', difusion_id, difusion.estado)
        return

    # Lock para evitar dos workers en paralelo sobre la misma difusión
    if not _acquire_lock(cache, difusion_id):
        logger.warning('Difusion %s already running (lock active), skipping', difusion_id)
        return

    try:
        Difusion.objects.filter(pk=difusion_id).update(
            estado=Difusion.ESTADO_ENVIANDO,
            enviado_at=timezone.now(),
        )

        pendientes = list(
            DifusionContacto.objects
            .filter(difusion_id=difusion_id, estado='pending')
            .select_related('contacto')
            .prefetch_related('contacto__valores__campo')
        )

        logger.info('Difusion %s: %d pending recipients', difusion_id, len(pendientes))

        if not pendientes:
            Difusion.objects.filter(pk=difusion_id).update(estado=Difusion.ESTADO_COMPLETADA)
            logger.info('Difusion %s: no pending recipients, marking completed', difusion_id)
            return

        usa_plantilla = difusion.plantilla_id is not None
        if usa_plantilla and difusion.plantilla.meta_estado != PlantillaHSM.ESTADO_APPROVED:
            logger.error(
                'Difusion %s: la plantilla "%s" no está aprobada por Meta (estado=%s)',
                difusion_id, difusion.plantilla.nombre, difusion.plantilla.meta_estado,
            )
            DifusionContacto.objects.filter(difusion_id=difusion_id, estado='pending').update(
                estado='failed', error='La plantilla no está aprobada por Meta.',
            )
            Difusion.objects.filter(pk=difusion_id).update(
                estado=Difusion.ESTADO_COMPLETADA, fallidos=F('fallidos') + len(pendientes),
            )
            return

        first = True

        for dc in pendientes:
            if not first:
                time.sleep(random.uniform(20, 40))
            first = False
            try:
                if usa_plantilla:
                    valores = [_personalizar(str(v), dc) for v in (difusion.variables_plantilla or [])]
                    mensaje = difusion.plantilla.preview(valores or None)
                    result = send_template_message(dc.telefono, difusion.plantilla, valores)
                else:
                    if not Conversacion.objects.filter(telefono=dc.telefono, ventana_activa=True).exists():
                        raise RuntimeError(
                            'Ventana de 24hs cerrada: Meta no permite texto libre fuera de la '
                            'ventana, hay que usar una Plantilla aprobada.'
                        )
                    mensaje = _personalizar(difusion.get_mensaje_texto(), dc)
                    result = send_text_message(dc.telefono, mensaje)

                msg_id = result.get('id', '')
                now = timezone.now()

                DifusionContacto.objects.filter(pk=dc.pk).update(
                    estado='sent',
                    whatsapp_message_id=msg_id,
                    enviado_at=now,
                )
                Difusion.objects.filter(pk=difusion_id).update(enviados=F('enviados') + 1)

                # Registrar en inbox
                try:
                    from apps.whatsapp.models import Mensaje
                    conv, created = Conversacion.objects.get_or_create(
                        telefono=dc.telefono,
                        defaults={
                            'nombre_contacto': dc.nombre or dc.telefono,
                            'contacto': dc.contacto,
                        },
                    )
                    if not created:
                        update_fields = {'ultimo_mensaje_at': now}
                        if not conv.contacto_id and dc.contacto_id:
                            update_fields['contacto_id'] = dc.contacto_id
                        if not conv.nombre_contacto and dc.nombre:
                            update_fields['nombre_contacto'] = dc.nombre
                        Conversacion.objects.filter(pk=conv.pk).update(**update_fields)
                    else:
                        Conversacion.objects.filter(pk=conv.pk).update(ultimo_mensaje_at=now)

                    Mensaje.objects.create(
                        conversacion=conv,
                        whatsapp_message_id=msg_id,
                        direccion=Mensaje.DIR_SALIENTE,
                        tipo=Mensaje.TIPO_PLANTILLA if usa_plantilla else Mensaje.TIPO_TEXTO,
                        contenido=mensaje,
                        status=Mensaje.STATUS_ENVIADO,
                        timestamp=now,
                    )
                except Exception as inbox_err:
                    logger.warning('Error registrando en inbox para %s: %s', dc.telefono, inbox_err)
            except Exception as e:
                logger.error('Difusion %s: error sending to %s: %s', difusion_id, dc.telefono, e)
                DifusionContacto.objects.filter(pk=dc.pk).update(
                    estado='failed',
                    error=str(e)[:500],
                )
                Difusion.objects.filter(pk=difusion_id).update(fallidos=F('fallidos') + 1)

        Difusion.objects.filter(pk=difusion_id).update(estado=Difusion.ESTADO_COMPLETADA)
        logger.info('Difusion %s completed', difusion_id)

    finally:
        _release_lock(difusion_id)
