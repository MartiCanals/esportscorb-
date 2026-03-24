from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required

def login_usuari(request):
    error = None
    if request.method == "POST":
        usuari = request.POST.get('username')
        clau = request.POST.get('password')
        user = authenticate(request, username=usuari, password=clau)
        if user is not None:
            login(request, user)
            return redirect('inici') # De moment ens torna a l'inici
        else:
            error = "Usuari o contrasenya incorrectes"
    
    return render(request, 'reservescorbera/login.html', {'error': error})

from django.contrib.auth.decorators import login_required

# Forcem la ruta aquí mateix per saltar-nos qualsevol configuració del settings
@login_required(login_url='/login/')  
def inici(request):
    return render(request, 'reservescorbera/inici.html')