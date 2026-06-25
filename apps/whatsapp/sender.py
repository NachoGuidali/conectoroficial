"""
Dispatcher de proveedor de WhatsApp.

Elige el backend (Meta Cloud API o Twilio) según el campo `proveedor` de la
configuración, y delega las llamadas. Las vistas, tasks y difusiones siguen
importando desde `apps.whatsapp.sender` sin enterarse del proveedor activo.
"""
from . import sender_meta, sender_twilio
from .media_utils import get_mediatype  # noqa: F401 (re-export para las vistas)

PROVEEDOR_META = 'meta'
PROVEEDOR_TWILIO = 'twilio'


def get_proveedor() -> str:
    from .models import ConfiguracionWhatsApp
    return ConfiguracionWhatsApp.get_setting('proveedor') or PROVEEDOR_META


def _backend():
    return sender_twilio if get_proveedor() == PROVEEDOR_TWILIO else sender_meta


def send_text_message(to, body):
    return _backend().send_text_message(to, body)


def send_media_message(to, media_url, mediatype, filename='', caption=''):
    return _backend().send_media_message(to, media_url, mediatype, filename=filename, caption=caption)


def send_interactive_message(to, body_text, buttons, header_text='', footer_text=''):
    return _backend().send_interactive_message(to, body_text, buttons, header_text=header_text, footer_text=footer_text)


def send_template_message(to, plantilla, valores=None):
    return _backend().send_template_message(to, plantilla, valores)


def get_phone_number_info():
    return _backend().get_phone_number_info()


def fetch_templates_from_meta():
    return _backend().fetch_templates_from_meta()


def create_template_on_meta(plantilla):
    return _backend().create_template_on_meta(plantilla)


def download_and_save_media(message_data, conv_pk):
    return _backend().download_and_save_media(message_data, conv_pk)
