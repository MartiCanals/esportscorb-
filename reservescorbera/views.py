from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User
from django.http import JsonResponse, Http404
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q  
from datetime import datetime
from .models import Instalacio, Reserva 

# 1. HOME PÚBLIC
def home(request):
    # 1. Agafem totes les instal·lacions
    instalacions = Instalacio.objects.all().order_by('nom')
    
    # 2. Creem un diccionari (context) amb la info comuna
    # Importat: afegim 'avui' per al calendari del qüestionari
    context = {
        'instalacions': instalacions,
        'avui': timezone.now().date()  # Això permet al HTML saber quin dia és avui
    }
    
    # 3. Decidim quina plantilla ensenyar
    if request.user.is_authenticated:
        # Si està loguejat, va directe a triar pista (calendari_instalacions.html)
        return render(request, 'reservescorbera/calendari_instalacions.html', context)
    
    # Si no, veu la home pública
    return render(request, 'reservescorbera/home.html', context)
# 2. LOGIN
def login_usuari(request):
    error = None
    if request.method == "POST":
        identificador = request.POST.get('username') 
        clau = request.POST.get('password')
        try:
            usuari_trobat = User.objects.get(email=identificador)
            user = authenticate(request, username=usuari_trobat.username, password=clau)
        except (User.DoesNotExist, User.MultipleObjectsReturned):
            user = authenticate(request, username=identificador, password=clau)

        if user is not None:
            login(request, user)
            return redirect('inici')
        else:
            error = "Dades incorrectes"
    return render(request, 'reservescorbera/login.html', {'error': error})

# 3. ÀREA PRIVADA
@login_required(login_url='/login/')
def inici(request):
    return render(request, 'reservescorbera/inici.html', {
        'les_meves_reserves': Reserva.objects.filter(entitat=request.user).order_by('-inici'),
        'instalacions': Instalacio.objects.all().order_by('nom'),
        'es_tecnic': request.user.is_staff
    })

# 4. FER RESERVA (DINÀMICA)
@login_required(login_url='/login/')
def fer_reserva(request, instalacio_id):
    instalacio = get_object_or_404(Instalacio, id=instalacio_id)
    
    dia = request.GET.get('data')
    hora_inici = request.GET.get('hora_inici')
    hora_fi = request.GET.get('hora_fi')
    
    # AGAFEM EL NOM DEL QÜESTIONARI
    # El busquem pel nom 'nom_activitat' que hem posat a l'HTML
    nom_activitat_real = request.GET.get('nom_activitat', 'Activitat')

    if dia and hora_inici and hora_fi:
        try:
            dt_inici = timezone.make_aware(datetime.strptime(f"{dia} {hora_inici}", "%Y-%m-%d %H:%M"))
            dt_fi = timezone.make_aware(datetime.strptime(f"{dia} {hora_fi}", "%Y-%m-%d %H:%M"))

            # Validació de solapament...
            solapament = Reserva.objects.filter(
                instalacio=instalacio,
                estat__in=['pendent', 'validada']
            ).filter(Q(inici__lt=dt_fi, final__gt=dt_inici)).exists()
            
            if solapament:
                messages.error(request, "Aquesta franja ja està ocupada.")
                return redirect('home')

            # FORMAT DEL TÍTOL PER AL CALENDARI:
            # Resultat: "marti - Sol·licitud: Entrenament Cadet"
            titol_per_calendari = f"{request.user.username} - Sol·licitud: {nom_activitat_real}"

            Reserva.objects.create(
                entitat=request.user, 
                instalacio=instalacio,
                activitat=titol_per_calendari, # Guardem el títol complet
                inici=dt_inici, 
                final=dt_fi, 
                estat='pendent'
            )
            
            messages.success(request, "Sol·licitud enviada!")
            return redirect('inici')
                
        except ValueError:
            messages.error(request, "Error de format.")
    
    return redirect('inici')
# 5. GESTIÓ TÈCNICA (STAFF)
@staff_member_required
def gestionar_reserves(request):
    # 1. Agafem totes les dades de la base de dades
    totes_les_reserves = Reserva.objects.all().order_by('-inici')[:50] # Últimes 50
    totes_les_instalacions = Instalacio.objects.all().order_by('nom')
    tots_els_usuaris = User.objects.all().order_by('username')

    # 2. LES PASSEM AL TEMPLATE (Això és el que et deu faltar)
    context = {
        'historial': totes_les_reserves,
        'instalacions': totes_les_instalacions,
        'usuaris': tots_els_usuaris,
    }
    
    return render(request, 'reservescorbera/gestio_tecnica.html', context)

# --- NOVA FUNCIÓ PER A TÈCNICS: CREAR INSTAL·LACIÓ ---
@staff_member_required
def crear_instalacio(request):
    if request.method == "POST":
        nom = request.POST.get('nom')
        color = request.POST.get('color', '#d4af37')
        imatge = request.FILES.get('imatge') # request.FILES per a fitxers!
        h_obertura = request.POST.get('hora_obertura', '08:00')
        h_tancament = request.POST.get('hora_tancament', '23:00')

        if nom:
            Instalacio.objects.create(
                nom=nom,
                color=color,
                imatge=imatge,
                hora_obertura=h_obertura,
                hora_tancament=h_tancament
            )
            messages.success(request, f"Instal·lació '{nom}' afegida correctament.")
            return redirect('gestionar_reserves')
        else:
            messages.error(request, "El nom és obligatori.")

    return render(request, 'reservescorbera/crear_instalacio.html')

# 6. EDITAR RESERVA
@staff_member_required
def editar_reserva(request, pk):
    reserva = get_object_or_404(Reserva, pk=pk)
    if request.method == "POST":
        reserva.activitat = request.POST.get('titol')
        reserva.estat = request.POST.get('estat')
        reserva.save()
        messages.success(request, "Reserva actualitzada.")
        return redirect('gestionar_reserves')
    return render(request, 'reservescorbera/editar_reserva.html', {'reserva': reserva})

# 7. ELIMINAR RESERVA
@staff_member_required
def eliminar_reserva(request, pk):
    reserva = get_object_or_404(Reserva, pk=pk)
    if request.method == "POST":
        reserva.delete()
        messages.success(request, "Reserva eliminada.")
    return redirect('gestionar_reserves')

# 8. APIs
def api_reserves(request):
    # Agafem les reserves (tant validades com pendents)
    reserves = Reserva.objects.filter(estat__in=['validada', 'pendent'])
    events = []
    
    for r in reserves:
        # Triem el color: gris si és pendent, color de la pista si és validada
        if r.estat == 'pendent':
            color_event = '#adb5bd'  # Gris clar
        else:
            color_event = r.instalacio.color if r.instalacio.color else '#d4af37'

        events.append({
            'id': r.id,
            # --- EL CANVI CLAU ÉS AQUÍ ---
            # r.activitat ja conté "NomUsuari - Sol·licitud: El que han escrit"
            'title': r.activitat, 
            
            'start': r.inici.isoformat(),
            'end': r.final.isoformat(),
            'backgroundColor': color_event,
            'borderColor': color_event,
            'extendedProps': {
                'instalacio': r.instalacio.nom,
                'estat': r.estat,
                'usuari': r.entitat.username
            }
        })
    return JsonResponse(events, safe=False)

def api_hores_ocupades(request):
    # Agafem els paràmetres tal com els envia el JavaScript del Modal
    # El JS envia 'data' i 'instalacio'
    dia_triat = request.GET.get('data') 
    inst_id = request.GET.get('instalacio')
    
    if not dia_triat or not inst_id:
        return JsonResponse([], safe=False)

    # Busquem les reserves per a aquella pista, aquell dia i que no estiguin rebutjades
    reserves = Reserva.objects.filter(
        instalacio_id=inst_id, 
        inici__date=dia_triat, 
        estat__in=['pendent', 'validada']
    )
    
    # El JavaScript del qüestionari espera una llista simple de strings: ["08:00", "09:00"]
    # strftime('%H:00') assegura que si la reserva és a les 10:30, la marqui com la franja de les 10:00 ocupada
    ocupades = [r.inici.strftime('%H:00') for r in reserves]
    
    # Eliminem duplicats si n'hi hagués
    ocupades = list(set(ocupades))
    
    return JsonResponse(ocupades, safe=False)

# 9. CONTEXT PROCESSOR / UTILITATS
def comptador_pendents(request):
    if request.user.is_authenticated and request.user.is_staff:
        quantes = Reserva.objects.filter(estat__iexact='pendent').count()
        return {'num_pendents': quantes}
    return {'num_pendents': 0}

    # 10. ELIMINAR INSTAL·LACIÓ (NOMÉS TÈCNICS)
@staff_member_required
def eliminar_instalacio(request, pk):
    # Intentem agafar la instal·lació o donem un error 404 si no existeix
    instalacio = get_object_or_404(Instalacio, pk=pk)
    
    if request.method == "POST":
        nom_pista = instalacio.nom
        instalacio.delete()
        messages.success(request, f"La instal·lació '{nom_pista}' s'ha eliminat correctament.")
    
    return redirect('gestionar_reserves')

@staff_member_required
def editar_instalacio(request, pk):
    instalacio = get_object_or_404(Instalacio, pk=pk)
    if request.method == "POST":
        instalacio.nom = request.POST.get('nom')
        instalacio.color = request.POST.get('color')
        instalacio.hora_obertura = request.POST.get('hora_obertura')
        instalacio.hora_tancament = request.POST.get('hora_tancament')
        
        if request.FILES.get('imatge'):
            instalacio.imatge = request.FILES.get('imatge')
            
        instalacio.save()
        messages.success(request, f"Instal·lació '{instalacio.nom}' actualitzada.")
        return redirect('gestionar_reserves')
        
    return render(request, 'reservescorbera/editar_instalacio.html', {'instalacio': instalacio})

# 12. CREAR USUARI/ENTITAT
@staff_member_required
def crear_usuari(request):
    if request.method == "POST":
        nom = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        tipus = request.POST.get('tipus') # Reblem el valor del select
        
        if User.objects.filter(username=nom).exists():
            messages.error(request, "Aquest nom d'usuari ja existeix.")
        else:
            nou_usuari = User.objects.create_user(username=nom, email=email, password=password)
            
            if tipus == "conserge":
                nou_usuari.is_staff = True
                nou_usuari.save()
                messages.success(request, f"Conserge '{nom}' creat amb èxit.")
            else:
                messages.success(request, f"Entitat '{nom}' creada amb èxit.")
                
            return redirect('/gestio-tecnica/#config')
            
    return render(request, 'reservescorbera/crear_usuari.html')

# 13. ELIMINAR USUARI
@staff_member_required
def eliminar_usuari(request, pk):
    usuari = get_object_or_404(User, pk=pk)
    if usuari.is_superuser:
        messages.error(request, "No es pot eliminar un superusuari.")
    else:
        nom = usuari.username
        usuari.delete()
        messages.success(request, f"L'entitat '{nom}' ha estat eliminada.")
    return redirect('/gestio-tecnica/#config')

@staff_member_required
def llista_pendents(request):
    if request.method == "POST":
        reserva_id = request.POST.get('reserva_id')
        accio = request.POST.get('accio')
        reserva = get_object_or_404(Reserva, id=reserva_id)
        
        if accio == 'validar':
            reserva.estat = 'validada'
            
            # --- AQUÍ ES FA LA MÀGIA ---
            # Si el títol era "Martí - Sol·licitud Pavelló", 
            # ara quedarà com "Martí - Pavelló"
            reserva.activitat = reserva.activitat.replace("Sol·licitud ", "")
            
            reserva.save()
            messages.success(request, "Reserva aprovada correctament!")
            
        elif accio == 'rebutjar':
            reserva.estat = 'rebutjada'
            reserva.save()
            messages.warning(request, "Reserva rebutjada.")
            
        return redirect('llista_pendents')

    pendents = Reserva.objects.filter(estat='pendent').order_by('inici')
    return render(request, 'reservescorbera/pendents.html', {'pendents': pendents})