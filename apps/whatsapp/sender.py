import json
import logging
import os
import time

import requests
from django.conf import settings

logger = logging.getLogger('apps.whatsapp')

GRAPH_BASE = 'https://graph.facebook.com'


def _cfg(key):
    from .models import ConfiguracionWhatsApp
    return ConfiguracionWhatsApp.get_setting(key)


def _access_token() -> str:
    return _cfg('meta_access_token') or getattr(settings, 'META_ACCESS_TOKEN', '')


def _api_version() -> str:
    return _cfg('meta_api_version') or getattr(settings, 'META_API_VERSION', 'v21.0')


def _phone_number_id() -> str:
    return _cfg('meta_phone_number_id') or getattr(settings, 'META_PHONE_NUMBER_ID', '')


def _waba_id() -> str:
    return _cfg('meta_waba_id') or getattr(settings, 'META_WABA_ID', '')


def _headers() -> dict:
    return {'Authorization': f'Bearer {_access_token()}', 'Content-Type': 'application/json'}


def _url(path: str) -> str:
    return f'{GRAPH_BASE}/{_api_version()}/{path}'


def _messages_url() -> str:
    return _url(f'{_phone_number_id()}/messages')


def _normalize_phone(phone: str) -> str:
    return phone.lstrip('+')


def _log_request(endpoint, method, request_body, response, duracion_ms):
    from .models import LogAPIWhatsApp
    try:
        LogAPIWhatsApp.objects.create(
            endpoint=endpoint, method=method,
            request_body=json.dumps(request_body) if isinstance(request_body, dict) else str(request_body),
            response_status=response.status_code if response else None,
            response_body=response.text[:5000] if response else '',
            duracion_ms=duracion_ms,
            exitoso=response is not None and response.status_code < 300,
        )
    except Exception:
        pass


def _extract_message_id(data: dict) -> str:
    messages = data.get('messages', [])
    return messages[0].get('id', '') if messages else ''


def _post_message(payload: dict, timeout: int = 15) -> dict:
    url = _messages_url()
    start = time.monotonic()
    response = None
    try:
        response = requests.post(url, json=payload, headers=_headers(), timeout=timeout)
        if not response.ok:
            logger.error('Meta API error %s: %s', response.status_code, response.text[:500])
        response.raise_for_status()
        return {'id': _extract_message_id(response.json())}
    except requests.RequestException as e:
        logger.error('Error sending message to %s: %s', payload.get('to'), e)
        raise
    finally:
        _log_request(url, 'POST', payload, response, int((time.monotonic() - start) * 1000))


def send_text_message(to: str, body: str) -> dict:
    payload = {
        'messaging_product': 'whatsapp',
        'to': _normalize_phone(to),
        'type': 'text',
        'text': {'body': body, 'preview_url': True},
    }
    return _post_message(payload)


def get_mediatype(mime: str) -> str:
    """Devuelve el tipo de medio para WhatsApp Cloud API según el MIME type."""
    if mime.startswith('image/'):
        return 'image'
    if mime.startswith('video/'):
        return 'video'
    if mime.startswith('audio/'):
        return 'audio'
    return 'document'


def send_media_message(to: str, media_url: str, mediatype: str, filename: str = '', caption: str = '') -> dict:
    media_obj = {'link': media_url}
    if caption and mediatype in ('image', 'video', 'document'):
        media_obj['caption'] = caption
    if filename and mediatype == 'document':
        media_obj['filename'] = filename
    payload = {
        'messaging_product': 'whatsapp',
        'to': _normalize_phone(to),
        'type': mediatype,
        mediatype: media_obj,
    }
    return _post_message(payload, timeout=30)


def send_interactive_message(to: str, body_text: str, buttons: list, header_text: str = '', footer_text: str = '') -> dict:
    interactive = {
        'type': 'button',
        'body': {'text': body_text},
        'action': {
            'buttons': [
                {'type': 'reply', 'reply': {'id': btn['id'], 'title': btn['title'][:20]}}
                for btn in buttons[:3]
            ],
        },
    }
    if header_text:
        interactive['header'] = {'type': 'text', 'text': header_text}
    if footer_text:
        interactive['footer'] = {'text': footer_text}
    payload = {
        'messaging_product': 'whatsapp',
        'to': _normalize_phone(to),
        'type': 'interactive',
        'interactive': interactive,
    }
    return _post_message(payload)


def send_template_message(to: str, plantilla, valores: list | None = None) -> dict:
    """Envía un mensaje usando una plantilla (HSM) aprobada por Meta."""
    components = []
    if valores:
        components.append({
            'type': 'body',
            'parameters': [{'type': 'text', 'text': str(v)} for v in valores],
        })
    payload = {
        'messaging_product': 'whatsapp',
        'to': _normalize_phone(to),
        'type': 'template',
        'template': {
            'name': plantilla.get_meta_nombre(),
            'language': {'code': plantilla.meta_idioma},
            'components': components,
        },
    }
    return _post_message(payload)


def get_phone_number_info() -> dict:
    """Devuelve verified_name, display_phone_number y quality_rating del número conectado."""
    url = _url(_phone_number_id())
    try:
        r = requests.get(
            url, headers=_headers(), timeout=10,
            params={'fields': 'verified_name,display_phone_number,quality_rating,code_verification_status'},
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error('Error fetching phone number info: %s', e)
        return {'error': str(e)}


def fetch_templates_from_meta() -> list:
    """Trae las plantillas registradas en la WABA, con su estado de aprobación."""
    url = _url(f'{_waba_id()}/message_templates')
    templates = []
    params = {'limit': 100}
    try:
        while url:
            r = requests.get(url, headers=_headers(), timeout=15, params=params)
            r.raise_for_status()
            data = r.json()
            templates.extend(data.get('data', []))
            url = data.get('paging', {}).get('next')
            params = None
    except Exception as e:
        logger.error('Error fetching templates from Meta: %s', e)
    return templates


def create_template_on_meta(plantilla) -> dict:
    """Crea (envía a revisión) una plantilla nueva en la WABA."""
    url = _url(f'{_waba_id()}/message_templates')
    payload = {
        'name': plantilla.get_meta_nombre(),
        'language': plantilla.meta_idioma,
        'category': plantilla.meta_categoria,
        'components': [{'type': 'BODY', 'text': plantilla.cuerpo}],
    }
    start = time.monotonic()
    response = None
    try:
        response = requests.post(url, json=payload, headers=_headers(), timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error('Error creating template on Meta: %s', e)
        body = {}
        try:
            body = response.json() if response is not None else {}
        except Exception:
            pass
        return {'error': str(e), 'detail': body}
    finally:
        _log_request(url, 'POST', payload, response, int((time.monotonic() - start) * 1000))


def download_and_save_media(media_id: str, conv_pk: int, filename: str = '') -> str:
    """
    Descarga un archivo de media de WhatsApp Cloud API (flujo de 2 pasos: metadata → URL
    temporal con Bearer) y lo guarda localmente. Devuelve la URL local o '' si falla.
    """
    try:
        meta_url = _url(media_id)
        r = requests.get(meta_url, headers=_headers(), timeout=15)
        if not r.ok:
            logger.warning('Media metadata %s: %s', r.status_code, r.text[:200])
            return ''
        meta = r.json()
        download_url = meta.get('url', '')
        mime = meta.get('mime_type', 'application/octet-stream')
        if not download_url:
            logger.warning('Sin url de descarga para media %s', media_id)
            return ''

        dl = requests.get(download_url, headers=_headers(), timeout=30)
        if not dl.ok:
            logger.warning('Descarga de media %s: %s', dl.status_code, dl.text[:200])
            return ''

        ext = _ext_from_mime(mime, filename)
        safe_name = f'{media_id[:32]}{ext}'
        upload_dir = os.path.join(settings.MEDIA_ROOT, 'uploads', f'conv_{conv_pk}')
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, safe_name)
        with open(file_path, 'wb') as f:
            f.write(dl.content)
        local_url = f'{settings.MEDIA_URL}uploads/conv_{conv_pk}/{safe_name}'
        logger.info('Media guardada: %s', local_url)
        return local_url
    except Exception as e:
        logger.error('Error descargando media %s: %s', media_id, e)
        return ''


def _ext_from_mime(mime: str, original_filename: str = '') -> str:
    """Devuelve la extensión correcta según el MIME type."""
    if original_filename and '.' in original_filename:
        return '.' + original_filename.rsplit('.', 1)[-1].lower()
    # Normalizar el MIME (quitar parámetros como "; codecs=opus")
    base_mime = mime.split(';')[0].strip().lower()
    mime_map = {
        'image/jpeg': '.jpg', 'image/jpg': '.jpg',
        'image/png': '.png', 'image/gif': '.gif',
        'image/webp': '.webp', 'image/heic': '.heic',
        'audio/ogg': '.ogg', 'audio/mpeg': '.mp3', 'audio/mp4': '.m4a',
        'audio/wav': '.wav', 'audio/opus': '.opus', 'audio/aac': '.aac',
        'video/mp4': '.mp4', 'video/3gpp': '.3gp', 'video/webm': '.webm',
        'application/pdf': '.pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
        'application/msword': '.doc', 'application/vnd.ms-excel': '.xls',
        'application/octet-stream': '.bin',
    }
    if base_mime in mime_map:
        return mime_map[base_mime]
    # Fallback por prefijo
    if base_mime.startswith('audio/'):
        return '.ogg'
    if base_mime.startswith('image/'):
        return '.jpg'
    if base_mime.startswith('video/'):
        return '.mp4'
    return '.bin'
