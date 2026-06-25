from django.contrib import admin
from django.urls import path, include, re_path
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', auth_views.LoginView.as_view(template_name='users/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('usuarios/', include('apps.users.urls', namespace='users')),
    path('whatsapp/', include('apps.whatsapp.urls', namespace='whatsapp')),
    path('contactos/', include('apps.contacts.urls', namespace='contacts')),
    path('difusiones/', include('apps.difusiones.urls', namespace='difusiones')),
    path('', include('apps.whatsapp.urls_home')),
    # Servir media siempre (DEBUG o producción) — Nginx también puede servir estos
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]
