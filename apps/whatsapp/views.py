import json
import logging
import re

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import ListView
from django.views.decorators.csrf import csrf_exempt

from apps.users.models import User
from .models import Conversacion, Mensaje, PlantillaHSM, ConfiguracionWhatsApp
from .tasks import process_incoming_message, send_whatsapp_message_task
from . import webhook_meta, webhook_twilio
from .sender import get_proveedor, PROVEEDOR_TWILIO

logger = logging.getLogger('apps.whatsapp')


class SupervisorRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_supervisor:
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden('Solo supervisores y administradores.')
        return super().dispatch(request, *args, **kwargs)


def _get_convs_qs(user, include_archived=False):
    from django.db.models import Q
    qs = Conversacion.objects.select_related('agente').order_by('-ultimo_mensaje_at', '-pk')
    if not include_archived:
        qs = qs.filter(archivada=False)
    if not user.can_see_all:
        qs = qs.filter(agente=user)
    return qs


@method_decorator(csrf_exempt, name='dispatch')
class WebhookView(View):
    def get(self, request):
        # Twilio no hace handshake GET; solo Meta lo usa al suscribir el webhook.
        if get_proveedor() == PROVEEDOR_TWILIO:
            return HttpResponse('OK', status=200)
        mode = request.GET.get('hub.mode', '')
        token = request.GET.get('hub.verify_token', '')
        challenge = request.GET.get('hub.challenge', '')
        configured_token = ConfiguracionWhatsApp.get_setting('meta_verify_token')
        if webhook_meta.verify_webhook_get(mode, token, configured_token):
            return HttpResponse(challenge, status=200)
        return HttpResponse('Forbidden', status=403)

    def post(self, request):
        if get_proveedor() == PROVEEDOR_TWILIO:
            return self._post_twilio(request)
        return self._post_meta(request)

    def _post_meta(self, request):
        app_secret = ConfiguracionWhatsApp.get_setting('meta_app_secret')
        signature = request.headers.get('X-Hub-Signature-256', '')
        if app_secret and not webhook_meta.verify_signature(request.body, signature, app_secret):
            logger.warning('Webhook rechazado — firma inválida')
            return HttpResponse('Forbidden', status=403)
        try:
            payload = json.loads(request.body)
            messages_data = webhook_meta.parse_incoming_webhook(payload)
            for msg_data in messages_data:
                process_incoming_message.delay(msg_data)
        except Exception as e:
            logger.exception('Webhook error: %s', e)
        return HttpResponse('OK', status=200)

    def _post_twilio(self, request):
        auth_token = ConfiguracionWhatsApp.get_setting('twilio_auth_token')
        signature = request.headers.get('X-Twilio-Signature', '')
        params = request.POST.dict()
        url = webhook_twilio.webhook_url(request)
        if auth_token and not webhook_twilio.validate_signature(url, params, signature, auth_token):
            logger.warning('Webhook Twilio rechazado — firma inválida')
            return HttpResponse('Forbidden', status=403)
        try:
            messages_data = webhook_twilio.parse_incoming_webhook(params)
            for msg_data in messages_data:
                process_incoming_message.delay(msg_data)
        except Exception as e:
            logger.exception('Webhook Twilio error: %s', e)
        # Twilio espera 200 con TwiML (puede ser vacío).
        return HttpResponse('<Response></Response>', content_type='text/xml', status=200)


class InboxView(LoginRequiredMixin, View):
    template_name = 'whatsapp/inbox.html'

    def get(self, request):
        from django.db.models import Q
        qs = _get_convs_qs(request.user)

        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(nombre_contacto__icontains=q) | Q(telefono__icontains=q))

        sin_agente = request.GET.get('sin_agente', '').strip()
        if sin_agente:
            qs = qs.filter(agente__isnull=True)

        solo_no_leidos = request.GET.get('no_leidos', '').strip()
        if solo_no_leidos:
            qs = qs.filter(mensajes_no_leidos__gt=0)

        archivadas = request.GET.get('archivadas', '').strip()
        if archivadas:
            # Mostrar archivadas en lugar de activas
            qs = Conversacion.objects.filter(archivada=True)
            if not request.user.can_see_all:
                qs = qs.filter(agente=request.user)
            qs = qs.order_by('-ultimo_mensaje_at')

        conversaciones = list(qs[:100])
        unread_total = _get_convs_qs(request.user).filter(mensajes_no_leidos__gt=0).count()

        # Conversación seleccionada
        selected_conv = None
        mensajes = []
        plantillas = []
        agents = None
        last_msg_id = 0

        contacto_campos = []
        conv_pk = request.GET.get('conv', '').strip()
        if conv_pk:
            try:
                # Si viene del filtro archivadas, buscar también en archivadas
                if archivadas:
                    conv_qs = Conversacion.objects.filter(archivada=True)
                    if not request.user.can_see_all:
                        conv_qs = conv_qs.filter(agente=request.user)
                else:
                    conv_qs = _get_convs_qs(request.user)
                selected_conv = (
                    conv_qs
                    .select_related('contacto')
                    .get(pk=int(conv_pk))
                )
                Conversacion.objects.filter(pk=selected_conv.pk).update(mensajes_no_leidos=0)
                msgs_qs = selected_conv.mensajes.order_by('timestamp')
                total = msgs_qs.count()
                mensajes = list(msgs_qs[max(0, total - 60):])
                plantillas = PlantillaHSM.objects.filter(activa=True)
                if request.user.can_see_all:
                    agents = User.objects.filter(is_active=True).order_by('first_name', 'username')
                last_msg = selected_conv.mensajes.order_by('timestamp').last()
                last_msg_id = last_msg.pk if last_msg else 0
                if selected_conv.contacto:
                    contacto_campos = selected_conv.contacto.get_campos_con_valores()
            except (Conversacion.DoesNotExist, ValueError):
                selected_conv = None

        return render(request, self.template_name, {
            'conversaciones': conversaciones,
            'unread_total': unread_total,
            'q': q,
            'sin_agente': sin_agente,
            'solo_no_leidos': solo_no_leidos,
            'archivadas': archivadas,
            'selected_conv': selected_conv,
            'mensajes': mensajes,
            'plantillas': plantillas,
            'agents': agents,
            'last_msg_id': last_msg_id,
            'contacto_campos': contacto_campos,
        })

    def post(self, request):
        conv_pk = request.POST.get('conv_pk', '').strip()
        if not conv_pk:
            return redirect('whatsapp:inbox')

        conv = get_object_or_404(_get_convs_qs(request.user, include_archived=True), pk=conv_pk)
        action = request.POST.get('action', '')

        if action == 'send_text':
            body = request.POST.get('body', '').strip()
            if body:
                if not conv.ventana_activa:
                    messages.error(
                        request,
                        'La ventana de 24hs para este contacto está cerrada. '
                        'Meta solo permite reabrirla con una Plantilla aprobada.',
                    )
                else:
                    msg = Mensaje.objects.create(
                        conversacion=conv, direccion=Mensaje.DIR_SALIENTE,
                        tipo=Mensaje.TIPO_TEXTO, contenido=body,
                        status=Mensaje.STATUS_PENDIENTE,
                        enviado_por=request.user, timestamp=timezone.now(),
                    )
                    send_whatsapp_message_task.delay(msg.pk)
                    Conversacion.objects.filter(pk=conv.pk).update(ultimo_mensaje_at=timezone.now())

        elif action == 'send_template':
            plantilla_id = request.POST.get('plantilla_id')
            if plantilla_id:
                plantilla = get_object_or_404(PlantillaHSM, pk=plantilla_id)
                if plantilla.meta_estado != PlantillaHSM.ESTADO_APPROVED:
                    messages.error(request, 'Esta plantilla todavía no está aprobada por Meta.')
                else:
                    vals = [request.POST.get(f'var_{i+1}', '') for i in range(len(plantilla.variables or []))]
                    valores = vals if any(vals) else []
                    text = plantilla.preview(valores or None)
                    try:
                        from .sender import send_template_message
                        result = send_template_message(conv.telefono, plantilla, valores)
                        Mensaje.objects.create(
                            conversacion=conv, direccion=Mensaje.DIR_SALIENTE,
                            tipo=Mensaje.TIPO_PLANTILLA, contenido=text,
                            whatsapp_message_id=result.get('id', ''),
                            status=Mensaje.STATUS_ENVIADO,
                            enviado_por=request.user, timestamp=timezone.now(),
                        )
                        Conversacion.objects.filter(pk=conv.pk).update(ultimo_mensaje_at=timezone.now())
                        messages.success(request, 'Plantilla enviada.')
                    except Exception as e:
                        messages.error(request, f'Error: {e}')

        params = f'conv={conv.pk}'
        if request.POST.get('_q'):
            params += f'&q={request.POST.get("_q")}'
        if request.POST.get('_archivadas'):
            params += '&archivadas=1'
        from django.urls import reverse
        return redirect(f"{reverse('whatsapp:inbox')}?{params}")


class ConversacionMessagesAPIView(LoginRequiredMixin, View):
    def get(self, request, pk):
        conv = get_object_or_404(_get_convs_qs(request.user, include_archived=True), pk=pk)
        since_id = int(request.GET.get('since_id', 0))
        nuevos = conv.mensajes.filter(pk__gt=since_id).order_by('timestamp')
        if nuevos.exists():
            Conversacion.objects.filter(pk=pk).update(mensajes_no_leidos=0)
        return JsonResponse({'mensajes': [{
            'id': m.pk, 'direccion': m.direccion, 'tipo': m.tipo,
            'contenido': m.contenido, 'media_url': m.media_url,
            'media_filename': m.media_filename, 'media_mime': m.media_mime,
            'status': m.status, 'timestamp': m.timestamp.strftime('%d/%m %H:%M'),
            'enviado_por': m.enviado_por.get_full_name() if m.enviado_por else '',
        } for m in nuevos]})


class DashboardSupervisorView(LoginRequiredMixin, View):
    template_name = 'whatsapp/dashboard_supervisor.html'

    def get(self, request):
        if not request.user.can_see_all:
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden()

        from django.contrib.auth import get_user_model
        from django.db.models import Count, Q as Qm
        User = get_user_model()

        agentes = (
            User.objects.filter(rol=User.ROL_AGENTE)
            .annotate(
                total=Count('conversaciones', filter=Qm(conversaciones__archivada=False)),
                bot=Count('conversaciones', filter=Qm(conversaciones__archivada=False, conversaciones__bot_n8n_activo=True)),
                pendiente=Count('conversaciones', filter=Qm(conversaciones__archivada=False, conversaciones__estado='pendiente')),
                abierta=Count('conversaciones', filter=Qm(conversaciones__archivada=False, conversaciones__estado='abierta', conversaciones__bot_n8n_activo=False)),
            )
            .order_by('-en_turno', 'username')
        )

        sin_asignar = Conversacion.objects.filter(
            agente__isnull=True, archivada=False
        ).order_by('-ultimo_mensaje_at')[:20]

        # Detalle de convs por agente (para el panel expandible)
        agente_pk = request.GET.get('agente')
        convs_agente = []
        agente_sel = None
        if agente_pk:
            try:
                agente_sel = User.objects.get(pk=agente_pk, rol=User.ROL_AGENTE)
                convs_agente = Conversacion.objects.filter(
                    agente=agente_sel, archivada=False
                ).order_by('-ultimo_mensaje_at').select_related('contacto')[:50]
            except User.DoesNotExist:
                pass

        return render(request, self.template_name, {
            'agentes': agentes,
            'sin_asignar': sin_asignar,
            'agente_sel': agente_sel,
            'convs_agente': convs_agente,
            'todos_agentes': User.objects.filter(rol=User.ROL_AGENTE, is_active=True).order_by('username'),
        })

    def post(self, request):
        """Reasignar todas las conversaciones de un agente a otro, o togglear su disponibilidad para la cola."""
        if not request.user.can_see_all:
            return JsonResponse({'ok': False, 'error': 'Sin permisos'}, status=403)

        from django.contrib.auth import get_user_model
        User = get_user_model()

        toggle_pk = request.POST.get('toggle_recibe_pk')
        if toggle_pk:
            agente = get_object_or_404(User, pk=toggle_pk, rol=User.ROL_AGENTE)
            agente.recibe_asignaciones = not agente.recibe_asignaciones
            agente.save(update_fields=['recibe_asignaciones'])
            return redirect(request.POST.get('next') or request.path)

        desde_pk = request.POST.get('desde_agente')
        hacia_pk = request.POST.get('hacia_agente') or None

        convs = Conversacion.objects.filter(agente_id=desde_pk, archivada=False)
        if hacia_pk:
            convs.update(agente_id=hacia_pk)
            msg = f'{convs.count()} conversaciones reasignadas.'
        else:
            # Redistribuir automáticamente
            from apps.whatsapp.tasks import auto_asignar_agente
            pks = list(convs.values_list('pk', flat=True))
            convs.update(agente=None)
            for conv in Conversacion.objects.filter(pk__in=pks):
                auto_asignar_agente(conv)
            msg = f'{len(pks)} conversaciones redistribuidas automáticamente.'

        from django.contrib import messages as msgs
        msgs.success(request, msg)
        return redirect(f"{request.path}?agente={desde_pk}")


class DashboardAgenteView(LoginRequiredMixin, View):
    template_name = 'whatsapp/dashboard_agente.html'

    def get(self, request):
        from django.db.models import Q as Qm
        convs = Conversacion.objects.filter(
            agente=request.user, archivada=False
        ).order_by('-ultimo_mensaje_at').select_related('contacto')

        bot_activo = convs.filter(bot_n8n_activo=True)
        pendientes = convs.filter(estado=Conversacion.ESTADO_PENDIENTE)
        abiertas = convs.filter(
            estado=Conversacion.ESTADO_ABIERTA, bot_n8n_activo=False
        )
        cerradas_hoy = Conversacion.objects.filter(
            agente=request.user,
            estado=Conversacion.ESTADO_CERRADA,
            ultimo_mensaje_at__date=timezone.now().date(),
        ).count()

        return render(request, self.template_name, {
            'bot_activo': bot_activo,
            'pendientes': pendientes,
            'abiertas': abiertas,
            'cerradas_hoy': cerradas_hoy,
            'total': convs.count(),
        })


class InboxUpdatesAPIView(LoginRequiredMixin, View):
    def get(self, request):
        qs = _get_convs_qs(request.user).filter(mensajes_no_leidos__gt=0)
        return JsonResponse({
            'unread_total': qs.count(),
            'conv_ids': list(qs.values_list('id', flat=True)),
        })


class InboxSSEView(LoginRequiredMixin, View):
    """
    Fast-polling SSE: responde en <100ms con los eventos disponibles y cierra.
    El browser reconecta cada 1.5s via EventSource retry.
    Cada worker solo está ocupado <100ms por request, nunca bloqueado.
    """

    def get(self, request):
        conv_pk = request.GET.get('conv_pk') or None
        last_msg_id = int(request.headers.get('Last-Event-ID') or
                          request.GET.get('last_msg_id') or 0)
        last_conv_ts = request.GET.get('last_conv_ts') or '0'

        events = []

        # ── Nuevos mensajes en la conversación activa ──────────────────
        if conv_pk:
            try:
                nuevos = list(
                    Mensaje.objects.filter(
                        conversacion_id=conv_pk,
                        pk__gt=last_msg_id,
                    ).order_by('pk').select_related('enviado_por')[:20]
                )
                for m in nuevos:
                    last_msg_id = m.pk
                    data = json.dumps({
                        'id': m.pk, 'tipo': m.tipo,
                        'contenido': m.contenido,
                        'direccion': m.direccion,
                        'media_url': m.media_url,
                        'media_filename': m.media_filename,
                        'media_mime': m.media_mime,
                        'timestamp': m.timestamp.strftime('%H:%M'),
                        'enviado_por': m.enviado_por.get_full_name() if m.enviado_por else '',
                    })
                    events.append(f'id: {m.pk}\nevent: message\ndata: {data}\n\n')
            except Exception:
                pass

        # ── Lista de conversaciones ────────────────────────────────────
        try:
            convs = list(
                _get_convs_qs(request.user)
                .order_by('-ultimo_mensaje_at')[:30]
                .values('pk', 'nombre_contacto', 'telefono',
                        'mensajes_no_leidos', 'ultimo_mensaje_at',
                        'archivada', 'estado')
            )
            conv_hash = str(hash(str([
                (c['pk'], c['mensajes_no_leidos'], str(c['ultimo_mensaje_at']), c['estado'])
                for c in convs
            ])))
            if conv_hash != last_conv_ts:
                for c in convs:
                    c['ultimo_mensaje_at'] = (
                        c['ultimo_mensaje_at'].strftime('%d/%m %H:%M')
                        if c['ultimo_mensaje_at'] else ''
                    )
                events.append(f'event: conv_list\ndata: {json.dumps({"convs": convs, "hash": conv_hash})}\n\n')
        except Exception:
            conv_hash = last_conv_ts

        # retry: 1500 → browser reconecta cada 1.5s
        body = 'retry: 1500\n\n' + ''.join(events)
        if not events:
            body += ': poll\n\n'

        response = HttpResponse(body, content_type='text/event-stream; charset=utf-8')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response


class NuevaConversacionView(LoginRequiredMixin, View):
    def post(self, request):
        telefono = request.POST.get('telefono', '').strip()
        nombre = request.POST.get('nombre', '').strip()
        contacto_id = request.POST.get('contacto_id', '').strip()

        if not telefono:
            messages.error(request, 'Ingresá un número de teléfono.')
            return redirect('whatsapp:inbox')
        if not telefono.startswith('+'):
            telefono = '+' + telefono

        # Try to find linked contact
        contacto = None
        try:
            from apps.contacts.models import Contacto
            if contacto_id:
                contacto = Contacto.objects.get(pk=int(contacto_id))
                telefono = contacto.telefono
                nombre = contacto.nombre
            else:
                try:
                    contacto = Contacto.objects.get(telefono=telefono)
                    nombre = nombre or contacto.nombre
                except Contacto.DoesNotExist:
                    pass
        except Exception:
            pass

        conv, _ = Conversacion.objects.get_or_create(
            telefono=telefono,
            defaults={
                'nombre_contacto': nombre or telefono,
                'agente': request.user,
                'contacto': contacto,
            },
        )
        if not conv.contacto and contacto:
            conv.contacto = contacto
            conv.save(update_fields=['contacto'])

        from django.urls import reverse
        return redirect(f"{reverse('whatsapp:inbox')}?conv={conv.pk}")


class AsignarAgenteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not request.user.can_see_all:
            return JsonResponse({'ok': False, 'error': 'Sin permisos'}, status=403)
        conv = get_object_or_404(Conversacion, pk=pk)
        agente_id = request.POST.get('agente_id') or None
        conv.agente_id = agente_id
        conv.save(update_fields=['agente_id'])
        agente_nombre = ''
        if agente_id:
            try:
                u = User.objects.get(pk=agente_id)
                agente_nombre = u.get_full_name() or u.username
            except User.DoesNotExist:
                pass
        return JsonResponse({'ok': True, 'agente_nombre': agente_nombre})


class ArchivarConversacionView(LoginRequiredMixin, View):
    def post(self, request, pk):
        conv = get_object_or_404(_get_convs_qs(request.user), pk=pk)
        conv.archivada = True
        conv.save(update_fields=['archivada'])
        return JsonResponse({'ok': True})


class DesarchivarConversacionView(LoginRequiredMixin, View):
    def post(self, request, pk):
        conv = get_object_or_404(Conversacion, pk=pk)
        conv.archivada = False
        conv.save(update_fields=['archivada'])
        return JsonResponse({'ok': True})


class MarcarLeidoView(LoginRequiredMixin, View):
    def post(self, request, pk):
        Conversacion.objects.filter(pk=pk).update(mensajes_no_leidos=0)
        return JsonResponse({'ok': True})


class AbrirConversacionView(LoginRequiredMixin, View):
    """Cuando el agente abre una conv pendiente, la pasa a 'abierta'."""
    def post(self, request, pk):
        Conversacion.objects.filter(pk=pk, estado=Conversacion.ESTADO_PENDIENTE).update(
            estado=Conversacion.ESTADO_ABIERTA
        )
        return JsonResponse({'ok': True})


class EnviarMediaView(LoginRequiredMixin, View):
    MAX_SIZE_MB = 16

    def post(self, request, pk):
        from .sender import send_media_message, get_mediatype

        conv = get_object_or_404(Conversacion, pk=pk)
        if not conv.ventana_activa:
            return JsonResponse({
                'ok': False,
                'error': 'La ventana de 24hs está cerrada. Usá una Plantilla aprobada para reabrirla.',
            }, status=400)

        archivo = request.FILES.get('archivo')
        caption = request.POST.get('caption', '').strip()

        if not archivo:
            return JsonResponse({'ok': False, 'error': 'No se recibió ningún archivo.'}, status=400)

        max_bytes = self.MAX_SIZE_MB * 1024 * 1024
        if archivo.size > max_bytes:
            return JsonResponse({'ok': False, 'error': f'El archivo supera los {self.MAX_SIZE_MB}MB.'}, status=400)

        import os
        from django.conf import settings as dj_settings

        mime = archivo.content_type or 'application/octet-stream'
        mediatype = get_mediatype(mime)
        filename = archivo.name or 'archivo'

        # Guardar localmente: WhatsApp Cloud API necesita una URL pública para descargarlo
        local_url = ''
        try:
            upload_dir = os.path.join(dj_settings.MEDIA_ROOT, 'uploads', f'conv_{pk}')
            os.makedirs(upload_dir, exist_ok=True)
            safe_name = re.sub(r'[^\w.\-]', '_', filename)
            local_path = os.path.join(upload_dir, safe_name)
            with open(local_path, 'wb') as f:
                for chunk in archivo.chunks():
                    f.write(chunk)
            local_url = f'{dj_settings.MEDIA_URL}uploads/conv_{pk}/{safe_name}'
        except Exception as save_err:
            logger.error('No se pudo guardar archivo localmente: %s', save_err)
            return JsonResponse({'ok': False, 'error': 'No se pudo guardar el archivo.'}, status=500)

        public_url = getattr(dj_settings, 'PUBLIC_URL', '').rstrip('/')
        external_url = f'{public_url}{local_url}' if public_url else request.build_absolute_uri(local_url)

        try:
            result = send_media_message(conv.telefono, external_url, mediatype, filename=filename, caption=caption)
            msg_id = result.get('id', '')
        except Exception as e:
            logger.error('Error enviando media a %s: %s', conv.telefono, e)
            return JsonResponse({'ok': False, 'error': f'Error al enviar el archivo: {str(e)[:100]}'}, status=500)

        # Registrar en DB
        tipo_map = {'image': Mensaje.TIPO_IMAGEN, 'video': Mensaje.TIPO_VIDEO,
                    'audio': Mensaje.TIPO_AUDIO, 'document': Mensaje.TIPO_DOCUMENTO}
        msg = Mensaje.objects.create(
            conversacion=conv,
            whatsapp_message_id=msg_id,
            direccion=Mensaje.DIR_SALIENTE,
            tipo=tipo_map.get(mediatype, Mensaje.TIPO_DOCUMENTO),
            contenido=caption,
            media_url=local_url,
            media_mime=mime,
            media_filename=filename,
            status=Mensaje.STATUS_ENVIADO,
            timestamp=timezone.now(),
            enviado_por=request.user,
        )
        Conversacion.objects.filter(pk=conv.pk).update(ultimo_mensaje_at=timezone.now())

        return JsonResponse({
            'ok': True,
            'mensaje': {
                'pk': msg.pk,
                'tipo': msg.tipo,
                'contenido': caption,
                'media_filename': filename,
                'media_mime': mime,
                'timestamp': msg.timestamp.strftime('%H:%M'),
                'enviado_por': request.user.get_full_name() or request.user.username,
            }
        })


class BotToggleView(LoginRequiredMixin, View):
    def post(self, request, pk):
        conv = get_object_or_404(Conversacion, pk=pk)
        bot_type = request.POST.get('bot_type', '')
        activo = request.POST.get('activo', 'true').lower() == 'true'
        if bot_type == 'crm':
            conv.bot_crm_activo = activo
            conv.save(update_fields=['bot_crm_activo'])
        elif bot_type == 'n8n':
            conv.bot_n8n_activo = activo
            conv.save(update_fields=['bot_n8n_activo'])
            if activo:
                from .tasks import liberar_asesor_n8n_task
                liberar_asesor_n8n_task.delay(conv.telefono)
        else:
            return JsonResponse({'ok': False, 'error': 'bot_type inválido'}, status=400)
        return JsonResponse({'ok': True, 'bot_type': bot_type, 'activo': activo})


class PlantillaListView(LoginRequiredMixin, ListView):
    model = PlantillaHSM
    template_name = 'whatsapp/plantilla_list.html'
    context_object_name = 'plantillas'
    paginate_by = 25


class PlantillaCreateView(LoginRequiredMixin, View):
    template_name = 'whatsapp/plantilla_form.html'

    # Todas las claves que el template puede leer vía `data.X`. Tienen que existir
    # siempre: cuando `data.X` se usa como argumento del filtro `default`, Django
    # re-lanza VariableDoesNotExist si falta la clave (no la silencia).
    EMPTY_DATA = {
        'nombre': '', 'cuerpo': '', 'variables_raw': '',
        'meta_nombre': '', 'meta_idioma': 'es_AR', 'meta_categoria': '',
        'twilio_content_sid': '',
    }

    def get(self, request):
        return render(request, self.template_name, {
            'data': dict(self.EMPTY_DATA),
            'CATEGORIA_CHOICES': PlantillaHSM.CATEGORIA_CHOICES,
            'proveedor': get_proveedor(),
            'PROVEEDOR_TWILIO': PROVEEDOR_TWILIO,
        })

    def post(self, request):
        nombre = request.POST.get('nombre', '').strip()
        cuerpo = request.POST.get('cuerpo', '').strip()
        if not nombre or not cuerpo:
            messages.error(request, 'Nombre y cuerpo son requeridos.')
            return render(request, self.template_name, {
                'data': {**self.EMPTY_DATA, **request.POST.dict()},
                'CATEGORIA_CHOICES': PlantillaHSM.CATEGORIA_CHOICES,
                'proveedor': get_proveedor(), 'PROVEEDOR_TWILIO': PROVEEDOR_TWILIO,
            })
        vars_raw = request.POST.get('variables_raw', '').strip()
        variables = [v.strip() for v in vars_raw.splitlines() if v.strip()] if vars_raw else []
        content_sid = request.POST.get('twilio_content_sid', '').strip()
        plantilla = PlantillaHSM.objects.create(
            nombre=nombre, cuerpo=cuerpo, variables=variables,
            meta_nombre=request.POST.get('meta_nombre', '').strip(),
            meta_idioma=request.POST.get('meta_idioma', '').strip() or 'es_AR',
            meta_categoria=request.POST.get('meta_categoria', '').strip() or PlantillaHSM.CATEGORIA_UTILITY,
            twilio_content_sid=content_sid,
        )
        if get_proveedor() == PROVEEDOR_TWILIO:
            # Con Twilio la plantilla ya está creada/aprobada en su consola; el ContentSid
            # la habilita para enviar fuera de la ventana de 24hs.
            if content_sid:
                plantilla.meta_estado = PlantillaHSM.ESTADO_APPROVED
                plantilla.save(update_fields=['meta_estado'])
                messages.success(request, 'Plantilla creada y vinculada al ContentSid de Twilio.')
            else:
                messages.warning(request, 'Plantilla creada, pero sin ContentSid no se puede enviar fuera de la ventana de 24hs.')
        elif request.POST.get('enviar_a_meta') == 'on':
            from .sender import create_template_on_meta
            result = create_template_on_meta(plantilla)
            if result.get('id'):
                plantilla.meta_template_id = result['id']
                plantilla.meta_estado = result.get('status', PlantillaHSM.ESTADO_PENDING)
                plantilla.save(update_fields=['meta_template_id', 'meta_estado'])
                messages.success(request, 'Plantilla creada y enviada a revisión de Meta.')
            else:
                detail = result.get('detail', {}).get('error', {}).get('message', '') or result.get('error', '')
                messages.warning(request, f'Plantilla creada localmente, pero falló el envío a Meta: {detail}')
        else:
            messages.success(request, 'Plantilla creada.')
        return redirect('whatsapp:plantilla_list')


class PlantillaUpdateView(LoginRequiredMixin, View):
    template_name = 'whatsapp/plantilla_form.html'

    def get(self, request, pk):
        p = get_object_or_404(PlantillaHSM, pk=pk)
        data = {
            'nombre': p.nombre or '', 'cuerpo': p.cuerpo or '',
            'meta_nombre': p.meta_nombre, 'meta_idioma': p.meta_idioma,
            'meta_categoria': p.meta_categoria,
            'twilio_content_sid': p.twilio_content_sid,
        }
        return render(request, self.template_name, {
            'obj': p, 'data': data, 'CATEGORIA_CHOICES': PlantillaHSM.CATEGORIA_CHOICES,
            'proveedor': get_proveedor(), 'PROVEEDOR_TWILIO': PROVEEDOR_TWILIO,
        })

    def post(self, request, pk):
        p = get_object_or_404(PlantillaHSM, pk=pk)
        p.nombre = request.POST.get('nombre', p.nombre).strip()
        p.cuerpo = request.POST.get('cuerpo', p.cuerpo).strip()
        vars_raw = request.POST.get('variables_raw', '').strip()
        p.variables = [v.strip() for v in vars_raw.splitlines() if v.strip()] if vars_raw else []
        p.meta_nombre = request.POST.get('meta_nombre', p.meta_nombre).strip()
        p.meta_idioma = request.POST.get('meta_idioma', p.meta_idioma).strip() or 'es_AR'
        p.meta_categoria = request.POST.get('meta_categoria', p.meta_categoria).strip()
        p.twilio_content_sid = request.POST.get('twilio_content_sid', p.twilio_content_sid).strip()
        p.activa = request.POST.get('activa') == 'on'
        # Con Twilio, un ContentSid presente habilita la plantilla para enviar fuera de la ventana.
        if get_proveedor() == PROVEEDOR_TWILIO and p.twilio_content_sid and p.meta_estado == PlantillaHSM.ESTADO_LOCAL:
            p.meta_estado = PlantillaHSM.ESTADO_APPROVED
        p.save()
        messages.success(request, 'Plantilla actualizada. Si ya estaba aprobada en Meta, el cambio de texto no se sincroniza solo: usá "Sincronizar desde Meta" o editala en Meta Business Manager.')
        return redirect('whatsapp:plantilla_list')


class PlantillaDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        get_object_or_404(PlantillaHSM, pk=pk).delete()
        messages.success(request, 'Plantilla eliminada.')
        return redirect('whatsapp:plantilla_list')


class SyncPlantillasView(SupervisorRequiredMixin, View):
    def post(self, request):
        from .tasks import sync_templates_from_meta
        actualizadas = sync_templates_from_meta()
        messages.success(request, f'Sincronizadas {actualizadas} plantilla(s) desde Meta.')
        return redirect('whatsapp:plantilla_list')


class ConfigView(SupervisorRequiredMixin, View):
    template_name = 'whatsapp/config.html'

    def get(self, request):
        try:
            config = ConfiguracionWhatsApp.objects.get(pk=1)
        except ConfiguracionWhatsApp.DoesNotExist:
            config = ConfiguracionWhatsApp()
        phone_info = {}
        if config.proveedor == ConfiguracionWhatsApp.PROVEEDOR_TWILIO:
            if config.twilio_account_sid and config.twilio_auth_token:
                from .sender import get_phone_number_info
                phone_info = get_phone_number_info()
        elif config.meta_access_token and config.meta_phone_number_id:
            from .sender import get_phone_number_info
            phone_info = get_phone_number_info()
        return render(request, self.template_name, {
            'config': config, 'phone_info': phone_info,
            'PROVEEDOR_CHOICES': ConfiguracionWhatsApp.PROVEEDOR_CHOICES,
        })

    def post(self, request):
        try:
            config = ConfiguracionWhatsApp.objects.get(pk=1)
        except ConfiguracionWhatsApp.DoesNotExist:
            config = ConfiguracionWhatsApp()
        config.proveedor = request.POST.get('proveedor', '').strip() or ConfiguracionWhatsApp.PROVEEDOR_META
        config.meta_access_token = request.POST.get('meta_access_token', '').strip()
        config.meta_phone_number_id = request.POST.get('meta_phone_number_id', '').strip()
        config.meta_waba_id = request.POST.get('meta_waba_id', '').strip()
        config.meta_app_secret = request.POST.get('meta_app_secret', '').strip()
        config.meta_verify_token = request.POST.get('meta_verify_token', '').strip()
        config.meta_api_version = request.POST.get('meta_api_version', '').strip() or 'v21.0'
        config.twilio_account_sid = request.POST.get('twilio_account_sid', '').strip()
        config.twilio_auth_token = request.POST.get('twilio_auth_token', '').strip()
        config.twilio_whatsapp_from = request.POST.get('twilio_whatsapp_from', '').strip()
        config.save()
        if config.proveedor == ConfiguracionWhatsApp.PROVEEDOR_TWILIO:
            messages.success(
                request,
                'Configuración guardada. En la consola de Twilio, configurá el webhook entrante '
                'apuntando a esta URL (método POST).',
            )
        else:
            messages.success(
                request,
                'Configuración guardada. Pegá la URL del webhook y el Verify Token en '
                'Meta for Developers → tu app → WhatsApp → Configuración.',
            )
        return redirect('whatsapp:config')


class ConnectionStatusView(LoginRequiredMixin, View):
    def get(self, request):
        from .sender import get_phone_number_info
        try:
            info = get_phone_number_info()
            if 'error' in info:
                return JsonResponse({'connected': False, 'detail': info['error']})
            return JsonResponse({'connected': True, **info})
        except Exception as e:
            return JsonResponse({'connected': False, 'detail': str(e)})


@method_decorator(csrf_exempt, name='dispatch')
class APIEnviarMensajeView(View):
    def post(self, request):
        from django.conf import settings as dj
        from .sender import send_text_message, send_media_message
        api_key = getattr(dj, 'CRM_API_KEY', '')
        if not api_key or request.headers.get('X-Api-Key', '') != api_key:
            return JsonResponse({'ok': False, 'error': 'Unauthorized'}, status=401)
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)
        # Aceptar 'phone' o 'telefono' indistintamente
        phone = (data.get('phone') or data.get('telefono') or '').strip()
        message = data.get('message', '').strip()
        media_url = data.get('media_url', '').strip()
        media_type = data.get('media_type', 'image')
        if not phone:
            return JsonResponse({'ok': False, 'error': '"phone" requerido'}, status=400)
        if not phone.startswith('+'):
            phone = '+' + phone
        conv, _ = Conversacion.objects.get_or_create(telefono=phone, defaults={'nombre_contacto': phone})
        if not conv.ventana_activa:
            return JsonResponse({
                'ok': False,
                'error': 'ventana_24h_expirada',
                'detail': 'La ventana de 24hs está cerrada. Hay que usar una Plantilla aprobada por Meta.',
            }, status=409)
        try:
            if media_url:
                result = send_media_message(phone, media_url, media_type, caption=message)
                tipo = Mensaje.TIPO_IMAGEN
            else:
                result = send_text_message(phone, message)
                tipo = Mensaje.TIPO_TEXTO
            msg = Mensaje.objects.create(
                conversacion=conv, direccion=Mensaje.DIR_SALIENTE, tipo=tipo,
                contenido=message, media_url=media_url,
                whatsapp_message_id=result.get('id', ''),
                status=Mensaje.STATUS_ENVIADO, timestamp=timezone.now(),
            )
            conv.ultimo_mensaje_at = timezone.now()
            conv.save(update_fields=['ultimo_mensaje_at'])
            return JsonResponse({'ok': True, 'message_id': result.get('id', ''), 'conversacion_id': conv.pk})
        except Exception as e:
            return JsonResponse({'ok': False, 'error': str(e)}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class APIContactoView(View):
    """
    Crea o actualiza un contacto en el CRM con datos adicionales.
    Los campos extra se guardan como CampoPersonalizado + ValorCampo.
    POST /whatsapp/api/contacto/
    Body: {
        "phone": "+549...",
        "nombre": "Juan García",        (opcional)
        "email": "juan@mail.com",       (opcional)
        "notas": "...",                 (opcional)
        "campos": {                     (opcional)
            "localidad": "Canning",
            "origen": "whatsapp",
            "obra_social": "UP"
        }
    }
    """
    def post(self, request):
        from django.conf import settings as dj
        api_key = getattr(dj, 'CRM_API_KEY', '')
        if not api_key or request.headers.get('X-Api-Key', '') != api_key:
            return JsonResponse({'ok': False, 'error': 'Unauthorized'}, status=401)
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)

        phone = (data.get('phone') or data.get('telefono') or '').strip()
        if not phone:
            return JsonResponse({'ok': False, 'error': '"phone" requerido'}, status=400)
        if not phone.startswith('+'):
            phone = '+' + phone

        from apps.contacts.models import Contacto, CampoPersonalizado, ValorCampo
        import re as _re

        nombre = data.get('nombre') or data.get('nombre_completo') or ''
        email = data.get('email', '')
        notas = data.get('notas', '')

        defaults = {}
        if nombre:
            defaults['nombre'] = nombre
        if email:
            defaults['email'] = email
        if notas:
            defaults['notas'] = notas

        contacto, created = Contacto.objects.get_or_create(
            telefono=phone,
            defaults={**defaults, 'nombre': nombre or phone},
        )
        if not created and defaults:
            for k, v in defaults.items():
                if v:
                    setattr(contacto, k, v)
            contacto.save()

        # Campos personalizados
        campos_data = data.get('campos') or {}
        campos_guardados = []
        for slug, valor in campos_data.items():
            if not slug or valor is None:
                continue
            slug_clean = _re.sub(r'[^\w]', '_', slug.lower().strip())[:100]
            etiqueta = slug.replace('_', ' ').title()
            campo, _ = CampoPersonalizado.objects.get_or_create(
                nombre=slug_clean,
                defaults={'etiqueta': etiqueta, 'tipo': 'text'},
            )
            ValorCampo.objects.update_or_create(
                contacto=contacto, campo=campo,
                defaults={'valor': str(valor)},
            )
            campos_guardados.append(slug_clean)

        # Vincular conversación si existe
        try:
            conv = Conversacion.objects.filter(telefono=phone, contacto__isnull=True).first()
            if conv:
                conv.contacto = contacto
                if nombre and not conv.nombre_contacto:
                    conv.nombre_contacto = nombre
                conv.save(update_fields=['contacto', 'nombre_contacto'])
        except Exception:
            pass

        return JsonResponse({
            'ok': True,
            'contacto_id': contacto.pk,
            'created': created,
            'campos_guardados': campos_guardados,
        })


@method_decorator(csrf_exempt, name='dispatch')
class APIBotToggleExternoView(View):
    """
    n8n puede prender/apagar el bot via API sin sesión de usuario.
    POST /whatsapp/api/bot/
    Body: {"conversation_id": 42, "activo": false}
      o:  {"phone": "+549...", "activo": true}
    """
    def post(self, request):
        from django.conf import settings as dj
        api_key = getattr(dj, 'CRM_API_KEY', '')
        if not api_key or request.headers.get('X-Api-Key', '') != api_key:
            return JsonResponse({'ok': False, 'error': 'Unauthorized'}, status=401)
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)

        activo = data.get('activo', False)
        conv = None
        if data.get('conversation_id'):
            conv = Conversacion.objects.filter(pk=data['conversation_id']).first()
        elif data.get('phone'):
            phone = data['phone']
            if not phone.startswith('+'): phone = '+' + phone
            conv = Conversacion.objects.filter(telefono=phone).first()

        if not conv:
            return JsonResponse({'ok': False, 'error': 'Conversación no encontrada'}, status=404)

        Conversacion.objects.filter(pk=conv.pk).update(bot_n8n_activo=activo)
        return JsonResponse({'ok': True, 'conversation_id': conv.pk, 'bot_n8n_activo': activo})


@method_decorator(csrf_exempt, name='dispatch')
class APIHandoffView(View):
    """
    n8n llama a este endpoint cuando el bot termina y quiere pasar la conv a un agente.
    Body JSON: {"conversation_id": 123}  o  {"phone": "+549..."}
    Header: X-Api-Key: <CRM_API_KEY>
    """
    def post(self, request):
        from django.conf import settings as dj
        api_key = getattr(dj, 'CRM_API_KEY', '')
        if not api_key or request.headers.get('X-Api-Key', '') != api_key:
            return JsonResponse({'ok': False, 'error': 'Unauthorized'}, status=401)
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)

        conv = None
        conv_id = data.get('conversation_id')
        phone = data.get('phone', '').strip()

        if conv_id:
            conv = Conversacion.objects.filter(pk=conv_id).first()
        elif phone:
            if not phone.startswith('+'):
                phone = '+' + phone
            conv = Conversacion.objects.filter(telefono=phone).first()

        if not conv:
            return JsonResponse({'ok': False, 'error': 'Conversación no encontrada'}, status=404)

        # Marcar como pendiente de agente y desactivar bot
        Conversacion.objects.filter(pk=conv.pk).update(
            estado=Conversacion.ESTADO_PENDIENTE,
            bot_n8n_activo=False,
        )
        logger.info('Handoff bot→agente para conv %s', conv.pk)
        return JsonResponse({'ok': True, 'conversation_id': conv.pk, 'estado': 'pendiente'})
