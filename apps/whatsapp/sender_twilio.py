"""Proveedor: Twilio WhatsApp API (BSP). Usa el SDK oficial `twilio`."""
import json
import logging
import os
import time

import requests
from django.conf import settings

from .media_utils import ext_from_mime, get_mediatype  # noqa: F401 (re-export)

logger = logging.getLogger('apps.whatsapp')

TWILIO_API_BASE = 'https://api.twilio.com'


def _cfg(key):
    from .models import ConfiguracionWhatsApp
    return ConfiguracionWhatsApp.get_setting(key)


def _account_sid() -> str:
    return _cfg('twilio_account_sid') or getattr(settings, 'TWILIO_ACCOUNT_SID', '')


def _auth_token() -> str:
    return _cfg('twilio_auth_token') or getattr(settings, 'TWILIO_AUTH_TOKEN', '')


def _whatsapp_from() -> str:
    """Número de WhatsApp habilitado en Twilio, con el prefijo whatsapp:."""
    raw = _cfg('twilio_whatsapp_from') or getattr(settings, 'TWILIO_WHATSAPP_FROM', '')
    raw = raw.strip()
    if not raw:
        return ''
    if not raw.startswith('whatsapp:'):
        raw = f'whatsapp:{raw}'
    return raw


def _wa(phone: str) -> str:
    """Normaliza un teléfono al formato whatsapp:+E164 que espera Twilio."""
    phone = phone.strip()
    if phone.startswith('whatsapp:'):
        return phone
    if not phone.startswith('+'):
        phone = '+' + phone.lstrip('+')
    return f'whatsapp:{phone}'


def _client():
    from twilio.rest import Client
    return Client(_account_sid(), _auth_token())


def _log(endpoint, method, request_body, status, response_text, exitoso, duracion_ms):
    from .models import LogAPIWhatsApp
    try:
        LogAPIWhatsApp.objects.create(
            endpoint=endpoint, method=method,
            request_body=json.dumps(request_body) if isinstance(request_body, dict) else str(request_body),
            response_status=status,
            response_body=(response_text or '')[:5000],
            duracion_ms=duracion_ms,
            exitoso=exitoso,
        )
    except Exception:
        pass


def _create_message(params: dict, timeout: int = 15) -> dict:
    """Envía un mensaje vía Twilio y devuelve {'id': MessageSid}."""
    from twilio.base.exceptions import TwilioRestException
    endpoint = f'{TWILIO_API_BASE}/2010-04-01/Accounts/{_account_sid()}/Messages.json'
    start = time.monotonic()
    try:
        msg = _client().messages.create(**params)
        dur = int((time.monotonic() - start) * 1000)
        _log(endpoint, 'POST', {k: v for k, v in params.items()}, 201, f'sid={msg.sid} status={msg.status}', True, dur)
        return {'id': msg.sid}
    except TwilioRestException as e:
        dur = int((time.monotonic() - start) * 1000)
        logger.error('Twilio API error %s: %s', getattr(e, 'status', '?'), e)
        _log(endpoint, 'POST', {k: v for k, v in params.items()}, getattr(e, 'status', None), str(e), False, dur)
        raise


def send_text_message(to: str, body: str) -> dict:
    return _create_message({
        'from_': _whatsapp_from(),
        'to': _wa(to),
        'body': body,
    })


def send_media_message(to: str, media_url: str, mediatype: str, filename: str = '', caption: str = '') -> dict:
    # Twilio no distingue el tipo: manda la URL en media_url y el texto en body.
    params = {
        'from_': _whatsapp_from(),
        'to': _wa(to),
        'media_url': [media_url],
    }
    if caption:
        params['body'] = caption
    return _create_message(params, timeout=30)


def send_interactive_message(to: str, body_text: str, buttons: list, header_text: str = '', footer_text: str = '') -> dict:
    # Twilio maneja botones vía Content templates (ContentSid), no en mensajes libres.
    # Como fallback, mandamos el texto del cuerpo como mensaje normal.
    texto = body_text
    if buttons:
        opciones = '\n'.join(f'- {b.get("title", "")}' for b in buttons)
        texto = f'{body_text}\n{opciones}'
    return send_text_message(to, texto)


def send_template_message(to: str, plantilla, valores: list | None = None) -> dict:
    """Envía una plantilla vía Twilio Content API (ContentSid + variables posicionales)."""
    content_sid = (getattr(plantilla, 'twilio_content_sid', '') or '').strip()
    if not content_sid:
        raise ValueError(
            'La plantilla no tiene ContentSid de Twilio. Creala en la consola de Twilio y '
            'pegá el ContentSid en la plantilla.'
        )
    params = {
        'from_': _whatsapp_from(),
        'to': _wa(to),
        'content_sid': content_sid,
    }
    if valores:
        params['content_variables'] = json.dumps(
            {str(i + 1): str(v) for i, v in enumerate(valores)}
        )
    return _create_message(params)


def get_phone_number_info() -> dict:
    """Valida credenciales y devuelve el número From configurado."""
    from twilio.base.exceptions import TwilioRestException
    desde = _whatsapp_from().replace('whatsapp:', '')
    try:
        account = _client().api.v2010.accounts(_account_sid()).fetch()
        return {
            'display_phone_number': desde,
            'verified_name': account.friendly_name,
            'quality_rating': account.status,  # active / suspended / closed
            'provider': 'twilio',
        }
    except TwilioRestException as e:
        logger.error('Error validando credenciales Twilio: %s', e)
        return {'error': str(e)}


def fetch_templates_from_meta() -> list:
    """Con Twilio las plantillas se gestionan manualmente (ContentSid). No hay sync automático."""
    return []


def create_template_on_meta(plantilla) -> dict:
    """No aplica con Twilio: las plantillas se crean en la consola de Twilio."""
    return {
        'error': 'Con Twilio las plantillas se crean en la consola de Twilio y se referencian '
                 'por ContentSid. Pegá el ContentSid en la plantilla.',
    }


def download_and_save_media(message_data: dict, conv_pk: int) -> str:
    """Descarga la media de un mensaje entrante de Twilio (URL directa con auth Basic)."""
    media_url = message_data.get('media_url', '')
    mime = message_data.get('media_mime', 'application/octet-stream')
    filename = message_data.get('media_filename', '')
    if not media_url:
        return ''
    try:
        dl = requests.get(media_url, auth=(_account_sid(), _auth_token()), timeout=30)
        if not dl.ok:
            logger.warning('Descarga de media Twilio %s: %s', dl.status_code, dl.text[:200])
            return ''
        if not mime or mime == 'application/octet-stream':
            mime = dl.headers.get('Content-Type', mime)

        ext = ext_from_mime(mime, filename)
        base = (message_data.get('message_id') or 'media')[:32]
        safe_name = f'{base}{ext}'
        upload_dir = os.path.join(settings.MEDIA_ROOT, 'uploads', f'conv_{conv_pk}')
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, safe_name)
        with open(file_path, 'wb') as f:
            f.write(dl.content)
        local_url = f'{settings.MEDIA_URL}uploads/conv_{conv_pk}/{safe_name}'
        logger.info('Media Twilio guardada: %s', local_url)
        return local_url
    except Exception as e:
        logger.error('Error descargando media Twilio: %s', e)
        return ''
