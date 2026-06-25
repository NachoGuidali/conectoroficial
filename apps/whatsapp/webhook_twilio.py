"""Parser de webhook: Twilio WhatsApp API (form-urlencoded + X-Twilio-Signature)."""
import logging

from django.conf import settings
from django.utils import timezone

from .media_utils import get_mediatype

logger = logging.getLogger('apps.whatsapp')

# Estados de entrega que Twilio reporta en los status callbacks.
_DELIVERY_STATUSES = {'queued', 'sending', 'sent', 'delivered', 'read', 'failed', 'undelivered'}
_STATUS_MAP = {
    'sent': 'sent', 'delivered': 'delivered', 'read': 'read',
    'failed': 'failed', 'undelivered': 'failed',
}


def validate_signature(url: str, params: dict, signature: str, auth_token: str) -> bool:
    """Valida la firma X-Twilio-Signature con el RequestValidator del SDK."""
    if not auth_token or not signature:
        return False
    try:
        from twilio.request_validator import RequestValidator
        return RequestValidator(auth_token).validate(url, params, signature)
    except Exception as e:
        logger.error('Error validando firma Twilio: %s', e)
        return False


def _strip_wa(phone: str) -> str:
    """'whatsapp:+549...' → '+549...'."""
    return phone.replace('whatsapp:', '').strip()


def parse_incoming_webhook(post: dict) -> list:
    """
    Procesa un POST de Twilio. Si es un status callback (mensaje saliente), actualiza
    el estado y devuelve []. Si es un mensaje entrante, devuelve el dict normalizado.
    """
    status = (post.get('MessageStatus') or post.get('SmsStatus') or '').lower()

    # Status callback de un mensaje que enviamos nosotros.
    if status in _DELIVERY_STATUSES and not post.get('Body') and not _num_media(post):
        _process_status(post, status)
        return []

    from_phone = _strip_wa(post.get('From', ''))
    if not from_phone:
        return []

    num_media = _num_media(post)
    media_url = post.get('MediaUrl0', '') if num_media else ''
    media_mime = post.get('MediaContentType0', '') if num_media else ''
    msg_type = get_mediatype(media_mime) if media_mime else 'text'

    content = post.get('Body', '')
    if not content and msg_type != 'text':
        content = f'[{msg_type.capitalize()}]'

    return [{
        'from_phone': from_phone,
        'message_id': post.get('MessageSid', '') or post.get('SmsMessageSid', ''),
        'type': msg_type,
        'content': content,
        'media_id': '',
        'media_url': media_url,
        'media_mime': media_mime,
        'media_filename': '',
        'timestamp': timezone.now(),
        'contact_name': post.get('ProfileName', ''),
    }]


def _num_media(post: dict) -> int:
    try:
        return int(post.get('NumMedia', '0') or '0')
    except (TypeError, ValueError):
        return 0


def _process_status(post: dict, status: str):
    from .models import Mensaje
    msg_id = post.get('MessageSid', '') or post.get('SmsSid', '')
    mapped = _STATUS_MAP.get(status)
    if not msg_id or not mapped:
        return
    update_fields = {'status': mapped}
    if mapped == 'failed':
        detalle = post.get('ErrorMessage', '') or post.get('ErrorCode', '')
        if detalle:
            update_fields['error_detalle'] = str(detalle)
    Mensaje.objects.filter(whatsapp_message_id=msg_id).update(**update_fields)


def webhook_url(request) -> str:
    """
    URL exacta que Twilio usó para llamar al webhook (necesaria para validar la firma).
    Detrás de Nginx forzamos https con PUBLIC_URL para que coincida con lo que firmó Twilio.
    """
    public = getattr(settings, 'PUBLIC_URL', '').rstrip('/')
    if public:
        return f'{public}{request.path}'
    return request.build_absolute_uri()
