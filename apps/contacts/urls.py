from django.urls import path
from . import views

app_name = 'contacts'

urlpatterns = [
    path('', views.ContactoListView.as_view(), name='list'),
    path('exportar/', views.ContactoExportarView.as_view(), name='exportar'),
    path('nuevo/', views.ContactoCreateView.as_view(), name='create'),
    path('<int:pk>/', views.ContactoDetailView.as_view(), name='detail'),
    path('<int:pk>/editar/', views.ContactoUpdateView.as_view(), name='update'),
    path('<int:pk>/eliminar/', views.ContactoDeleteView.as_view(), name='delete'),

    path('campos/', views.CampoListView.as_view(), name='campos'),
    path('campos/nuevo/', views.CampoCreateView.as_view(), name='campo_create'),
    path('campos/<int:pk>/editar/', views.CampoUpdateView.as_view(), name='campo_update'),
    path('campos/<int:pk>/eliminar/', views.CampoDeleteView.as_view(), name='campo_delete'),

    path('importar/', views.ImportarContactosView.as_view(), name='importar'),

    path('grupos/', views.GruposListView.as_view(), name='grupos'),
    path('grupos/asignar/', views.GrupoAsignarView.as_view(), name='grupo_asignar'),
    path('grupos/eliminar/', views.GrupoEliminarView.as_view(), name='grupo_eliminar'),

    path('api/buscar/', views.ContactoBuscarAPIView.as_view(), name='buscar_api'),
    path('api/campos/', views.CamposParaGrupoAPIView.as_view(), name='campos_api'),
]
