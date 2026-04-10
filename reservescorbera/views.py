from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from .models import Instalacio  # Importem el model que hem omplert amb el CSV

# 1. La Pàgina Pública (la que acabem de dissenyar)
def home(request):
    instalacions = Instalacio.objects.all()
    return render(request, 'reservescorbera/home.html', {'instalacions': instalacions})

# 2. La teva vista de Login (la que ja tenies)
def login_usuari(request):
    error = None
    if request.method == "POST":
        usuari = request.POST.get('username')
        clau = request.POST.get('password')
        user = authenticate(request, username=usuari, password=clau)
        if user is not None:
            login(request, user)
            return redirect('inici')
        else:
            error = "Usuari o contrasenya incorrectes"
    
    return render(request, 'reservescorbera/login.html', {'error': error})

# 3. La zona privada del club (després de fer login)
@login_required(login_url='/login/')  
def inici(request):
    return render(request, 'reservescorbera/inici.html')