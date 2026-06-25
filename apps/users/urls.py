from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    path('', views.UserListView.as_view(), name='list'),
    path('nuevo/', views.UserCreateView.as_view(), name='create'),
    path('<int:pk>/editar/', views.UserUpdateView.as_view(), name='update'),
    path('<int:pk>/toggle/', views.UserToggleView.as_view(), name='toggle'),
    path('turno/', views.TurnoToggleView.as_view(), name='turno_toggle'),
]
