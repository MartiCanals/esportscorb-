from django.urls import path
from . import views  # El punt (.) significa "importa les views d'aquesta mateixa carpeta"

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login_usuari, name='login'),
    path('inici/', views.inici, name='inici'),
]