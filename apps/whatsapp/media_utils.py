"""Utilidades de media compartidas entre proveedores (Meta / Twilio)."""


def get_mediatype(mime: str) -> str:
    """Devuelve el tipo de medio (image/video/audio/document) según el MIME type."""
    if mime.startswith('image/'):
        return 'image'
    if mime.startswith('video/'):
        return 'video'
    if mime.startswith('audio/'):
        return 'audio'
    return 'document'


def ext_from_mime(mime: str, original_filename: str = '') -> str:
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
