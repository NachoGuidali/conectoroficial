def unread_messages_count(request):
    if not request.user.is_authenticated:
        return {'unread_messages_count': 0}
    from .models import Conversacion
    qs = Conversacion.objects.filter(mensajes_no_leidos__gt=0, archivada=False)
    if not request.user.can_see_all:
        qs = qs.filter(agente=request.user)
    return {'unread_messages_count': qs.count()}
