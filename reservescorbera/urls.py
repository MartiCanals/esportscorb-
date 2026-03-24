from django.urls import path
from . import views

urlpatterns = [
    path('', views.inici, name='inici'),
    path('login/', views.login_usuari, name='login'), # Revisa que la barra / estigui al final
]
