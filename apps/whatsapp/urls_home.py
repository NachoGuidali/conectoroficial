from django.urls import path
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


def home_redirect(request):
    if not request.user.is_authenticated:
        return redirect('login')
    if request.user.rol == 'agente':
        return redirect('whatsapp:dashboard')
    if request.user.can_see_all:
        return redirect('whatsapp:dashboard_supervisor')
    return redirect('whatsapp:inbox')


urlpatterns = [
    path('', login_required(home_redirect), name='home'),
]
