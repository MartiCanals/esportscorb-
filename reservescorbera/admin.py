from django.contrib import admin
from .models import Instalacio, Reserva # Importem els teus models

admin.site.register(Instalacio)
admin.site.register(Reserva)
