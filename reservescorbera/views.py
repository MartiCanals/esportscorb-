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
from .forms import UserProfileForm  # El punt (.) vol dir "en aquesta mateixa carpeta"
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from datetime import timedelta

# 1. HOME PÚBLIC
def home(request):
    # 1. Tornem a carregar les instal·lacions perquè el menú desplegable les trobi
    instalacions = Instalacio.objects.all().order_by('nom')
    
    # 2. Les fiquem al context
    context = {
        'instalacions': instalacions,
        'avui': timezone.now().date()
    }
    
    # 3. Ara el template 'home.html' ja tindrà les dades per al desplegable
    return render(request, 'reservescorbera/home.html', context)

@login_required
def inici(request):
    # 1. PROCESSAR ACCIONS DEL TÈCNIC
    if request.method == "POST" and request.user.is_staff:
        reserva_id = request.POST.get('reserva_id')
        accio = request.POST.get('accio')
        try:
            reserva = Reserva.objects.get(id=reserva_id)
            if accio == 'validar':
                reserva.estat = 'validada'  # OK: Coincideix amb el teu Model
            elif accio == 'rebutjar':
                reserva.estat = 'rebutjada' # CANVIAT: Abans deies 'anul·lada', però al model és 'rebutjada'
            reserva.save()
        except Reserva.DoesNotExist:
            pass
        return redirect('/inici/?gestio=1')

    # 2. DADES PER AL TÈCNIC (Filtratge de dades velles)
    pendents = []
    num_pendents = 0
    if request.user.is_staff:
        from django.utils import timezone
        ara = timezone.now()
        
        # Filtrem perquè NO surtin les reserves que ja han passat de data
        pendents = Reserva.objects.filter(
            estat='pendent',
            inici__gte=ara  # Només les que comencen ara o en el futur
        ).order_by('inici')
        num_pendents = pendents.count()

    # 3. DADES PER A L'USUARI
    instalacions = Instalacio.objects.all().order_by('nom')
    les_meves_reserves = Reserva.objects.filter(entitat=request.user).order_by('-inici')

    context = {
        'instalacions': instalacions,
        'les_meves_reserves': les_meves_reserves,
        'pendents': pendents,
        'num_pendents': num_pendents,
        'es_tecnic': request.user.is_staff
    }
    
    return render(request, 'reservescorbera/inici.html', context)

@login_required
def calendari_pistes(request):
    # Aquesta ja la tenies bé, és la que carrega el calendari de reserves
    instalacions = Instalacio.objects.all().order_by('nom')
    context = {
        'instalacions': instalacions,
        'avui': timezone.now().date()
    }
    return render(request, 'reservescorbera/calendari_instalacions.html', context)
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



# 4. FER RESERVA (DINÀMICA)
@login_required
def fer_reserva(request, instalacio_id):
    instalacio = get_object_or_404(Instalacio, id=instalacio_id)
    dia = request.GET.get('data')
    hora_inici = request.GET.get('hora_inici')
    hora_fi = request.GET.get('hora_fi')
    nom_activitat = request.GET.get('nom_activitat', 'Activitat')

    if dia and hora_inici and hora_fi:
        try:
            # Creem objectes datetime conscients de la zona horària
            dt_inici = timezone.make_aware(datetime.strptime(f"{dia} {hora_inici}", "%Y-%m-%d %H:%M"))
            dt_fi = timezone.make_aware(datetime.strptime(f"{dia} {hora_fi}", "%Y-%m-%d %H:%M"))

            # COMPROVACIÓ CRÍTICA: Hi ha alguna reserva que se solapi?
            solapament = Reserva.objects.filter(
                instalacio=instalacio,
                estat__in=['pendent', 'validada']
            ).filter(
                Q(inici__lt=dt_fi, final__gt=dt_inici) # La lògica matemàtica de solapament
            ).exists()

            if solapament:
                messages.error(request, "Aquesta franja horària s'ha ocupat mentrestant. Tria'n una altra.")
                return redirect('calendari_instalacions') # Torna al selector de pistes

            # Si no hi ha solapament, creem
            Reserva.objects.create(
                entitat=request.user,
                instalacio=instalacio,
                activitat=f"{request.user.username} - {nom_activitat}",
                inici=dt_inici,
                final=dt_fi,
                estat='pendent'
            )
            messages.success(request, "Sol·licitud enviada correctament!")
            return redirect('inici')

        except Exception as e:
            messages.error(request, f"Error en processar la reserva: {e}")
    
    return redirect('inici')
# 5. GESTIÓ TÈCNICA (STAFF)
@staff_member_required
def gestionar_reserves(request):
    totes_les_reserves = Reserva.objects.all().order_by('-inici')[:50]
    totes_les_instalacions = Instalacio.objects.all().order_by('nom')
    
    # Filtrem aquí l'usuari marti
    usuaris_filtrats = User.objects.exclude(username='marti').order_by('username')

    context = {
        'historial': totes_les_reserves,
        'instalacions': totes_les_instalacions,
        'usuaris': usuaris_filtrats, # Envia la llista filtrada!
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
def api_hores_ocupades(request):
    dia_triat = request.GET.get('data') 
    inst_id = request.GET.get('instalacio')
    
    if not dia_triat or not inst_id:
        return JsonResponse([], safe=False)

    # 1. Busquem les reserves. 
    # Filtrem per instal·lació i data, només les que NO estan rebutjades.
    reserves = Reserva.objects.filter(
        instalacio_id=inst_id, 
        inici__date=dia_triat, 
        estat__in=['pendent', 'validada']
    )
    
    ocupades = []
    
    for r in reserves:
        # 2. CONVERSIÓ A HORA LOCAL (Molt important)
        # Si Django usa Timezones, convertim l'hora de la BD a l'hora que veu l'usuari
        inici_local = timezone.localtime(r.inici)
        final_local = timezone.localtime(r.final)
        
        actual = inici_local
        while actual < final_local:
            # Afegim l'hora en format "HH:MM" (ex: "09:15")
            ocupades.append(actual.strftime('%H:%M'))
            actual += timedelta(minutes=15)
            
    # 3. Retornem la llista única (set) per evitar duplicats
    return JsonResponse(list(set(ocupades)), safe=False)

from django.utils import timezone
from datetime import timedelta
from django.http import JsonResponse

def api_hores_ocupades(request):
    dia_triat = request.GET.get('data') 
    inst_id = request.GET.get('instalacio')
    
    if not dia_triat or not inst_id:
        return JsonResponse([], safe=False)

    # 1. Busquem les reserves. 
    reserves = Reserva.objects.filter(
        instalacio_id=inst_id, 
        inici__date=dia_triat, 
        estat__in=['pendent', 'validada']
    )
    
    ocupades = set() # Usem un set per evitar duplicats automàticament
    
    for r in reserves:
        # Convertim a hora local perquè coincideixi amb el que l'usuari veu al formulari
        # Si no uses zones horàries, r.inici i r.final ja estaran bé
        inici = timezone.localtime(r.inici)
        final = timezone.localtime(r.final)
        
        actual = inici
        # EL TRUC: Mentre sigui MENOR que el final (no menor o igual)
        # Si la reserva acaba a les 15:15, el bucle s'atura a les 15:00
        while actual < final:
            ocupades.add(actual.strftime('%H:%M'))
            actual += timedelta(minutes=15)
            
    # Retornem la llista ordenada
    return JsonResponse(sorted(list(ocupades)), safe=False)
def api_reserves(request):
    if request.user.is_authenticated and request.user.is_staff:
        # El tècnic ho veu tot
        reserves = Reserva.objects.all()
    else:
        # Entitats i públic només validades
        reserves = Reserva.objects.filter(estat='validada')
    
    events = []
    for r in reserves:
        # Color base de la instal·lació
        color_base = r.instalacio.color or '#d4af37'
        titol = r.activitat
        
        # Propietats per defecte (Validades)
        background_color = color_base
        border_color = color_base
        text_color = '#ffffff' # Text blanc per a les validades

        if r.estat == 'pendent':
            # Si és pendent: Gris fosc amb 50% de transparència
            background_color = 'rgba(108, 117, 125, 0.5)' 
            border_color = 'rgba(108, 117, 125, 0.8)'
            text_color = '#495057' # Text gris fosc per contrastar amb el fons translúcid
            
        elif r.estat == 'rebutjada':
            background_color = 'rgba(220, 53, 69, 0.2)' # Vermell molt tènue
            border_color = '#dc3545'
            text_color = '#dc3545'

        events.append({
            'id': r.id,
            'title': titol,
            'start': r.inici.isoformat(),
            'end': r.final.isoformat(),
            'backgroundColor': background_color,
            'borderColor': border_color,
            'textColor': text_color,
            'extendedProps': {
                'instalacio': r.instalacio.nom,
                'estat': r.estat
            }
        })
    return JsonResponse(events, safe=False)
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

@login_required
def pistes(request):
    # Agafem les dades que necessita el calendari
    instalacions = Instalacio.objects.all().order_by('nom')
    
    context = {
        'instalacions': instalacions,
        'avui': timezone.now().date()
    }
    
    # IMPORTAT: Aquí carreguem directament la plantilla de les pistes
    return render(request, 'reservescorbera/calendari_instalacions.html', context)

    from django.http import JsonResponse
from django.views.decorators.http import require_POST

@staff_member_required
@require_POST
def accio_reserva(request):
    reserva_id = request.POST.get('id')
    accio = request.POST.get('accio')
    reserva = get_object_or_404(Reserva, id=reserva_id)

    if accio == 'eliminar':
        reserva.delete()
    elif accio == 'editar':
        nou_titol = request.POST.get('titol')
        nou_estat = request.POST.get('estat')
        if nou_titol: reserva.activitat = nou_titol
        if nou_estat: reserva.estat = nou_estat
        reserva.save()

    # Recalculem el total de pendents per actualitzar la campaneta
    num_pendents = Reserva.objects.filter(estat='pendent').count()

    return JsonResponse({
        'status': 'ok',
        'msg': 'Operació realitzada',
        'num_pendents': num_pendents,
        'estat_final': reserva.estat,
        'reserva': { # Enviem dades per si hem de "tornar a crear" la targeta
            'id': reserva.id,
            'activitat': reserva.activitat,
            'inici': reserva.inici.strftime('%H:%M'),
            'final': reserva.final.strftime('%H:%M'),
            'data': reserva.inici.strftime('%d/%m'),
            'entitat': reserva.entitat.username,
            'instalacio': reserva.instalacio.nom,
            'color': reserva.instalacio.color or '#d4af37'
        }
    })


@login_required
def perfil(request):
    # Preparem els dos formularis buits o amb les dades actuals de l'usuari
    perfil_form = UserProfileForm(instance=request.user)
    password_form = PasswordChangeForm(request.user)

    if request.method == 'POST':
        # CAS A: L'usuari vol canviar el CORREU
        if 'btn_perfil' in request.POST:
            perfil_form = UserProfileForm(request.POST, instance=request.user)
            if perfil_form.is_valid():
                perfil_form.save()
                messages.success(request, 'Correu actualitzat correctament!')
                return redirect('perfil')

        # CAS B: L'usuari vol canviar la CONTRASENYA
        elif 'btn_password' in request.POST:
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                # Aquesta línia és vital: evita que l'usuari sigui expulsat de la sessió en canviar la pass
                update_session_auth_hash(request, user)
                messages.success(request, 'Contrasenya actualitzada correctament!')
                return redirect('perfil')
            else:
                messages.error(request, 'Si us plau, corregeix els errors de la contrasenya.')

    # Enviem els dos formularis al template
    return render(request, 'reservescorbera/perfil.html', {
        'perfil_form': perfil_form,
        'password_form': password_form
    })