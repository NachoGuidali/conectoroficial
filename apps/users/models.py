from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROL_ADMIN = 'admin'
    ROL_SUPERVISOR = 'supervisor'
    ROL_AGENTE = 'agente'
    ROL_CHOICES = [
        (ROL_ADMIN, 'Administrador'),
        (ROL_SUPERVISOR, 'Supervisor'),
        (ROL_AGENTE, 'Agente'),
    ]

    rol = models.CharField(max_length=20, choices=ROL_CHOICES, default=ROL_AGENTE)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    telefono = models.CharField(max_length=20, blank=True)
    en_turno = models.BooleanField(default=True, verbose_name='En turno')
    recibe_asignaciones = models.BooleanField(default=True, verbose_name='Recibe asignaciones automáticas')

    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    def __str__(self):
        return f'{self.get_full_name() or self.username} ({self.get_rol_display()})'

    @property
    def is_admin(self):
        return self.rol == self.ROL_ADMIN or self.is_superuser

    @property
    def is_supervisor(self):
        return self.rol in (self.ROL_ADMIN, self.ROL_SUPERVISOR) or self.is_superuser

    @property
    def can_see_all(self):
        """Admin y supervisor ven todas las conversaciones."""
        return self.is_supervisor
