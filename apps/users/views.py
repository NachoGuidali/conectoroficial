from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from .models import User


class AdminRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_admin:
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden('Solo administradores.')
        return super().dispatch(request, *args, **kwargs)


class UserListView(AdminRequiredMixin, View):
    template_name = 'users/list.html'

    def get(self, request):
        users = User.objects.all().order_by('rol', 'username')
        return render(request, self.template_name, {'users': users})


class UserCreateView(AdminRequiredMixin, View):
    template_name = 'users/form.html'

    def get(self, request):
        data = {'username': '', 'first_name': '', 'last_name': '', 'email': '', 'telefono': '', 'rol': ''}
        return render(request, self.template_name, {'rol_choices': User.ROL_CHOICES, 'data': data})

    def post(self, request):
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        rol = request.POST.get('rol', User.ROL_AGENTE)
        telefono = request.POST.get('telefono', '').strip()
        password = request.POST.get('password', '').strip()
        recibe_asignaciones = request.POST.get('recibe_asignaciones') == 'on'

        if not username or not password:
            messages.error(request, 'Usuario y contraseña son requeridos.')
            return render(request, self.template_name, {'rol_choices': User.ROL_CHOICES, 'data': request.POST.dict()})

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Ese nombre de usuario ya existe.')
            return render(request, self.template_name, {'rol_choices': User.ROL_CHOICES, 'data': request.POST.dict()})

        user = User.objects.create_user(
            username=username, email=email, password=password,
            first_name=first_name, last_name=last_name,
            rol=rol, telefono=telefono, recibe_asignaciones=recibe_asignaciones,
        )
        messages.success(request, f'Usuario {user.username} creado.')
        return redirect('users:list')


class UserUpdateView(AdminRequiredMixin, View):
    template_name = 'users/form.html'

    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        data = {
            'first_name': user.first_name or '',
            'last_name': user.last_name or '',
            'email': user.email or '',
            'telefono': getattr(user, 'telefono', '') or '',
            'rol': user.rol or '',
            'recibe_asignaciones': user.recibe_asignaciones,
        }
        return render(request, self.template_name, {'obj': user, 'rol_choices': User.ROL_CHOICES, 'data': data})

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        user.email = request.POST.get('email', '').strip()
        user.first_name = request.POST.get('first_name', '').strip()
        user.last_name = request.POST.get('last_name', '').strip()
        user.rol = request.POST.get('rol', user.rol)
        user.telefono = request.POST.get('telefono', '').strip()
        user.recibe_asignaciones = request.POST.get('recibe_asignaciones') == 'on'
        password = request.POST.get('password', '').strip()
        if password:
            user.set_password(password)
        user.save()
        messages.success(request, 'Usuario actualizado.')
        return redirect('users:list')


class TurnoToggleView(LoginRequiredMixin, View):
    """El agente activa/desactiva su disponibilidad para recibir conversaciones."""
    def post(self, request):
        user = request.user
        user.en_turno = not user.en_turno
        user.save(update_fields=['en_turno'])
        return JsonResponse({'ok': True, 'en_turno': user.en_turno})


class UserToggleView(AdminRequiredMixin, View):
    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        if user == request.user:
            return JsonResponse({'ok': False, 'error': 'No podés desactivarte a vos mismo.'})
        was_active = user.is_active
        user.is_active = not user.is_active
        user.save(update_fields=['is_active'])

        # Si se desactiva un agente, redistribuir sus conversaciones abiertas
        if was_active and not user.is_active and user.rol == User.ROL_AGENTE:
            _redistribuir_conversaciones(user)

        return JsonResponse({'ok': True, 'is_active': user.is_active})


def _redistribuir_conversaciones(agente_desactivado):
    """
    Reasigna las conversaciones abiertas del agente desactivado
    a otros agentes activos (menor carga primero).
    """
    from apps.whatsapp.models import Conversacion
    from apps.whatsapp.tasks import auto_asignar_agente

    # Guardar PKs antes de desasignar
    conv_pks = list(
        Conversacion.objects.filter(agente=agente_desactivado, archivada=False)
        .values_list('pk', flat=True)
    )
    count = len(conv_pks)
    if not count:
        return

    # Desasignar primero para que auto_asignar no cuente al agente desactivado
    Conversacion.objects.filter(pk__in=conv_pks).update(agente=None)

    # Reasignar de a una para distribuir carga equitativamente
    for conv in Conversacion.objects.filter(pk__in=conv_pks):
        auto_asignar_agente(conv)

    import logging
    logging.getLogger('apps.whatsapp').info(
        'Redistribuidas %d conversaciones del agente desactivado %s',
        count, agente_desactivado.username
    )
