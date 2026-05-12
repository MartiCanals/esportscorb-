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
from .models import Instalacio, Reserva, PlantillaReserva, ActivitatExtra
from .forms import UserProfileForm  # El punt (.) vol dir "en aquesta mateixa carpeta"
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from datetime import timedelta
import re
from django.core.mail import send_mail
from django.conf import settings

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
    # 1. PROCESSAR ACCIONS DEL TÈCNIC (POST)
    if request.method == "POST" and request.user.is_staff:
        reserva_id = request.POST.get('reserva_id')
        accio = request.POST.get('accio')
        try:
            reserva = Reserva.objects.get(id=reserva_id)
            if accio == 'validar':
                reserva.estat = 'validada'
            elif accio == 'rebutjar':
                reserva.estat = 'rebutjada'
            reserva.save()
        except Reserva.DoesNotExist:
            pass
        return redirect('/inici/?gestio=1')

    # 2. DADES PER AL TÈCNIC / CONSERGE
    pendents = []
    num_pendents = 0
    conserges = [] # Llista buida per defecte
    
    if request.user.is_staff:
        ara = timezone.now()
        
        # Filtrem perquè NO surtin les reserves pendents passades
        pendents = Reserva.objects.filter(
            estat='pendent',
            inici__gte=ara
        ).order_by('inici')
        num_pendents = pendents.count()
        
        # OBTENIR ELS CONSERGES PER AL DESPLEGABLE
        # Busquem el grup anomenat 'Conserge'
        grup_conserge = Group.objects.filter(name='Conserge').first()
        if grup_conserge:
            conserges = grup_conserge.user_set.all().order_by('username')

    # 3. DADES GENERALS
    instalacions = Instalacio.objects.all().order_by('nom')
    les_meves_reserves = Reserva.objects.filter(entitat=request.user).order_by('-inici')

    context = {
        'instalacions': instalacions,
        'les_meves_reserves': les_meves_reserves,
        'pendents': pendents,
        'num_pendents': num_pendents,
        'conserges': conserges,  # <--- ARA SÍ: Arribarà al JS del SweetAlert
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

    if not dia or not hora_inici or not hora_fi:
        return redirect('calendari_instalacions')

    try:
        # Convertim a objectes datetime conscients de la zona horària
        dt_inici = timezone.make_aware(datetime.strptime(f"{dia} {hora_inici}", "%Y-%m-%d %H:%M"))
        dt_fi = timezone.make_aware(datetime.strptime(f"{dia} {hora_fi}", "%Y-%m-%d %H:%M"))

        # 1. PROTECCIÓ ANTI-DUPLICATS (Evita el problema del doble clic/fantasma)
        # Si ja existeix exactament la mateixa reserva per aquest usuari, no fem res.
        duplicat_propi = Reserva.objects.filter(
            entitat=request.user,
            instalacio=instalacio,
            inici=dt_inici,
            final=dt_fi
        ).exists()

        if duplicat_propi:
            # Si és un duplicat de la mateixa persona, el portem a l'inici sense avisar d'error
            return redirect('inici')

        # 2. VALIDACIÓ DE SOLAPAMENT (Amb altres reserves)
        solapament = Reserva.objects.filter(
            instalacio=instalacio,
            estat__in=['pendent', 'validada']
        ).filter(
            Q(inici__lt=dt_fi, final__gt=dt_inici)
        ).exists()

        if solapament:
            messages.error(request, "Aquesta franja s'ha ocupat. Tria'n una altra.")
            return redirect('calendari_instalacions')

        # 3. CREACIÓ DE LA RESERVA
        nom_usuari = request.user.username.upper()
        titol_visible = f"{nom_usuari}: {nom_activitat}"

        Reserva.objects.create(
            entitat=request.user,
            instalacio=instalacio,
            activitat=titol_visible,
            inici=dt_inici,
            final=dt_fi,
            estat='pendent'
        )
        
        messages.success(request, "Sol·licitud enviada correctament!")
        return redirect('inici')

    except Exception as e:
        messages.error(request, f"Error en processar la reserva: {e}")
        return redirect('calendari_instalacions')

# 5. GESTIÓ TÈCNICA (STAFF)
# BUSCA LA FUNCIÓ QUE COMENÇA A LA LÍNIA 129 I DEIXA-LA AIXÍ:
@staff_member_required
def gestio_tecnica(request):  # <--- Canviem el nom perquè coincideixi amb urls.py
    totes_les_reserves = Reserva.objects.all().order_by('-inici')[:50]
    totes_les_instalacions = Instalacio.objects.all().order_by('nom')
    
    # Filtrem aquí l'usuari marti
    usuaris_filtrats = User.objects.exclude(username='marti').order_by('username')

    context = {
        'historial': totes_les_reserves,
        'instalacions': totes_les_instalacions,
        'usuaris': usuaris_filtrats, 
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
            return redirect('gestio_tecnica')
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

@staff_member_required
def eliminar_extra(request, pk):
    # Busquem l'activitat extra (avís daurat)
    activitat = get_object_or_404(ActivitatExtra, pk=pk)
    activitat.delete()
    messages.success(request, "Activitat extraordinària eliminada.")
    return redirect('activitats_extra')

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
from .models import Reserva, ActivitatExtra  # Assegura't d'importar el nou model

def api_reserves(request):
    es_staff = request.user.is_authenticated and request.user.is_staff
    # Check de grup segur per a usuaris anònims
    es_conserge = request.user.is_authenticated and request.user.groups.filter(name="Conserge").exists()

    # 1. FILTRE DE RESERVES (Aquí apliquem la seguretat)
    if es_staff:
        reserves = Reserva.objects.all()
    else:
        # Pels usuaris públics: només validades I que NO siguin de conserge
        reserves = Reserva.objects.filter(estat='validada').exclude(activitat__icontains='CONSERGE')
    
    events = []

    # 1. RESERVES DE PISTES
    for r in reserves:
        try:
            color_base = r.instalacio.color or '#d4af37'
            
            events.append({
                'id': r.id,
                'title': r.activitat,
                'start': r.inici.isoformat(),
                'end': r.final.isoformat(),
                'backgroundColor': color_base if r.estat != 'pendent' else 'rgba(108, 117, 125, 0.5)',
                'borderColor': color_base,
                'textColor': '#ffffff',
                'extendedProps': {
                    'instalacio': r.instalacio.nom,
                    'estat': r.estat,
                    'tipus': 'reserva'
                }
            })
        except Exception as e:
            print(f"Error en reserva {r.id}: {e}")

    # 2. ACTIVITATS EXTRA (Avisos daurats)
    # He mogut això FORA de l'if es_staff perquè vols que el públic vegi els avisos de manteniment, etc.
    # Però només si l'usuari és staff/conserge o si vols que siguin públiques. 
    # Si vols que les Activitats Extra siguin PÚBLIQUES, treu el "if es_staff or es_conserge:"
    
    if es_staff or es_conserge: # Canvia aquesta condició si vols que les extres siguin públiques
        try:
            activitats_extra = ActivitatExtra.objects.all()
            for act in activitats_extra:
                if act.data and act.inici and act.final:
                    events.append({
                        'id': f"extra-{act.id}",
                        'title': act.titol,
                        'start': f"{act.data.strftime('%Y-%m-%d')}T{act.inici.strftime('%H:%M:%S')}",
                        'end': f"{act.data.strftime('%Y-%m-%d')}T{act.final.strftime('%H:%M:%S')}",
                        'backgroundColor': '#d4af37', # Color daurat per a les extres
                        'textColor': '#1a1a1a',
                        'extendedProps': {
                            'tipus': 'extra',
                            'instalacio': 'AVÍS GLOBAL'
                        }
                    })
        except Exception as e:
            print(f"Error carregant Activitats Extra: {e}")

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
    
    return redirect('gestio_tecnica')

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
        return redirect('gestio_tecnica')
        
    return render(request, 'reservescorbera/editar_instalacio.html', {'instalacio': instalacio})

# 12. CREAR USUARI/ENTITAT
from django.contrib.auth.models import User, Group # Important importar Group

@staff_member_required
def crear_usuari(request):
    if request.method == "POST":
        nom = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        tipus = request.POST.get('tipus')
        
        if User.objects.filter(username=nom).exists():
            messages.error(request, "Aquest nom d'usuari ja existeix.")
        else:
            nou_usuari = User.objects.create_user(username=nom, email=email, password=password)
            
            if tipus == "conserge":
                # 1. Donem accés a l'àrea privada
                nou_usuari.is_staff = True
                nou_usuari.save()
                
                # 2. Assignem el grup 'Conserge'
                # get_or_create assegura que el grup existeixi a la base de dades
                grup_conserge, created = Group.objects.get_or_create(name='Conserge')
                nou_usuari.groups.add(grup_conserge)
                
                messages.success(request, f"Conserge '{nom}' creat amb èxit.")
            else:
                # Si és entitat, no és staff i no té grup (usuari ras)
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
    reserva_id_raw = request.POST.get('id')
    accio = request.POST.get('accio')
    
    # Netegem la ID: traiem qualsevol lletra (com "extra-") i ens quedem amb el número
    reserva_id = re.sub(r'\D', '', str(reserva_id_raw))

    # A. CAS CREAR
    if accio == 'crear_directe':
        titol = request.POST.get('titol')
        inici = request.POST.get('inici')
        final = request.POST.get('final')
        
        reserva = Reserva.objects.create(
            activitat=titol,
            inici=inici,
            final=final,
            instalacio=Instalacio.objects.first(),
            entitat=request.user,
            estat='validada'
        )
        return JsonResponse({
            'status': 'ok',
            'num_pendents': Reserva.objects.filter(estat='pendent').count(),
            'estat_final': 'validada'
        })

    # B. GESTIÓ EXISTENTS
    reserva = Reserva.objects.filter(id=reserva_id).first()
    extra = ActivitatExtra.objects.filter(id=reserva_id).first()
    
    estat_final = 'pendent'

    if accio == 'eliminar':
        if extra:
            extra.delete()
        elif reserva:
            reserva.delete()
        estat_final = 'eliminada'
    
    elif accio == 'editar':
        nou_titol = request.POST.get('titol')
        nou_estat = request.POST.get('estat')
        
        if extra:
            if nou_titol: extra.titol = nou_titol
            extra.save()
            estat_final = 'validada'
        elif reserva:
            if nou_titol: reserva.activitat = nou_titol
            if nou_estat: reserva.estat = nou_estat
            reserva.save()
            estat_final = reserva.estat

    # AQUEST RETURN ÉS EL QUE EVITA EL "RETURNED NONE"
    return JsonResponse({
        'status': 'ok',
        'num_pendents': Reserva.objects.filter(estat='pendent').count(),
        'estat_final': estat_final
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



from datetime import datetime, timedelta

from datetime import datetime, timedelta

@login_required
def aplicar_plantilla_al_calendari(request):
    if request.user.is_staff:
        from .models import PlantillaReserva, Reserva
        from django.utils import timezone
        
        # 1. Intentem capturar la data de qualsevol d'aquestes dues variables
        data_str = request.GET.get('data_inici') or request.GET.get('data_dilluns')
        
        # Aquest print t'ha de sortir amb la data ara sí!
        print(f"\n---> DATA DETECTADA: {data_str}\n")
        
        if data_str:
            try:
                dia_referencia = datetime.strptime(data_str, '%Y-%m-%d').date()
            except ValueError:
                dia_referencia = timezone.now().date()
        else:
            dia_referencia = timezone.now().date()

        # 2. CALCULEM EL DILLUNS (Això és el que mou les reserves de lloc)
        dilluns_setmana = dia_referencia - timedelta(days=dia_referencia.weekday())
        
        plantilla = PlantillaReserva.objects.all()
        creades = 0
        
        for item in plantilla:
            # IMPORTANT: Fem servir 'dilluns_setmana' per calcular el dia exacte
            data_reserva = dilluns_setmana + timedelta(days=item.dia_setmana)
            
            dt_inici = timezone.make_aware(datetime.combine(data_reserva, item.inici))
            dt_final = timezone.make_aware(datetime.combine(data_reserva, item.final))

            hi_ha_solapament = Reserva.objects.filter(
                instalacio=item.instalacio,
                inici__lt=dt_final,
                final__gt=dt_inici
            ).exclude(estat='rebutjada').exists()

            if not hi_ha_solapament:
                nom_usuari = item.user.username.upper()
                Reserva.objects.create(
                    entitat=item.user,
                    instalacio=item.instalacio,
                    inici=dt_inici,
                    final=dt_final,
                    activitat=f"{nom_usuari}: {item.activitat}",
                    estat='validada'
                )
                creades += 1
            
        messages.success(request, f"✨ Plantilla aplicada a la setmana del {dilluns_setmana.strftime('%d/%m/%Y')}")
    
    return redirect('inici')
@login_required
def gestio_plantilla(request):
    # 1. SEGURETAT: Només l'staff pot gestionar la plantilla
    if not request.user.is_staff:
        return redirect('inici')
    
    if request.method == 'POST':
        try:
            dia = int(request.POST.get('dia_setmana'))
            inst_id = request.POST.get('instalacio')
            h_inici_str = request.POST.get('inici')
            h_final_str = request.POST.get('final')
            
            # Convertim els valors del formulari a objectes de temps
            t_inici = datetime.strptime(h_inici_str, '%H:%M').time()
            t_final = datetime.strptime(h_final_str, '%H:%M').time()
            
            inst = Instalacio.objects.get(id=inst_id)

            # --- VALIDACIÓ 1: Horari d'obertura/tancament de la pista ---
            if t_inici < inst.hora_obertura or t_final > inst.hora_tancament:
                messages.error(request, f"Error: {inst.nom} només obre de {inst.hora_obertura.strftime('%H:%M')} a {inst.hora_tancament.strftime('%H:%M')}.")
                return redirect('gestio_plantilla')

            # --- VALIDACIÓ 2: Coherència (Inici abans que Final) ---
            if t_inici >= t_final:
                messages.error(request, "L'hora d'inici ha de ser anterior a la de final.")
                return redirect('gestio_plantilla')

            # --- VALIDACIÓ 3: No solapaments (Dues coses alhora) ---
            solapament = PlantillaReserva.objects.filter(
                dia_setmana=dia,
                instalacio=inst,
                inici__lt=t_final,  # Si algun existent comença abans que el nou acabi
                final__gt=t_inici   # Si algun existent acaba després que el nou comenci
            ).exists()

            if solapament:
                messages.error(request, f"Ja hi ha una activitat a {inst.nom} en aquesta franja horària.")
                return redirect('gestio_plantilla')

            # Si tot està bé, guardem
            PlantillaReserva.objects.create(
                dia_setmana=dia,
                instalacio=inst,
                user_id=request.POST.get('usuari'),
                inici=t_inici,
                final=t_final,
                activitat=request.POST.get('activitat')
            )
            messages.success(request, "Entrenament fix afegit correctament.")
            
        except Exception as e:
            messages.error(request, f"S'ha produït un error: {e}")
            
        return redirect('gestio_plantilla')

    # --- PREPARACIÓ DE DADES PER AL RENDER ---
    
    # Elements ordenats cronològicament
    elements = PlantillaReserva.objects.all().order_by('inici')
    instalacions = Instalacio.objects.all()
    usuaris = User.objects.exclude(username='marti').order_by('username')
    
    # Generem totes les franges possibles de 15 minuts (8h a 24h)
    franges = [f"{h:02d}:{m:02d}" for h in range(8, 24) for m in [0, 15, 30, 45]]
    
    dies_setmana = [
        (0, 'Dilluns'), (1, 'Dimarts'), (2, 'Dimecres'), (3, 'Dijous'), 
        (4, 'Divendres'), (5, 'Dissabte'), (6, 'Diumenge')
    ]

    # Diccionari d'horaris per passar-lo al JavaScript del HTML
    horaris_pistes_js = {
        str(i.id): {
            'obertura': i.hora_obertura.strftime('%H:%M'),
            'tancament': i.hora_tancament.strftime('%H:%M')
        } for i in instalacions
    }

    return render(request, 'reservescorbera/gestio_plantilla.html', {
        'elements': elements,
        'instalacions': instalacions,
        'usuaris': usuaris,
        'dies_setmana': dies_setmana,
        'franges': franges,
        'horaris_js': horaris_pistes_js  # Aquest és el que fa que el JS funcioni
    })

@login_required
def eliminar_plantilla(request, pk):
    if request.user.is_staff:
        item = PlantillaReserva.objects.get(pk=pk)
        item.delete()
        messages.success(request, "Entrenament eliminat de la plantilla.")
    return redirect('gestio_plantilla')

@login_required
def editar_plantilla(request, pk):
    if not request.user.is_staff:
        return redirect('inici')
    
    item = PlantillaReserva.objects.get(pk=pk)
    
    if request.method == 'POST':
        item.dia_setmana = int(request.POST.get('dia_setmana'))
        item.instalacio_id = request.POST.get('instalacio')
        item.user_id = request.POST.get('usuari')
        item.inici = request.POST.get('inici')
        item.final = request.POST.get('final')
        item.activitat = request.POST.get('activitat')
        
        # Aquí podries repetir les validacions de solapament que hem fet abans
        item.save()
        messages.success(request, "Entrenament actualitzat correctament.")
        return redirect('gestio_plantilla')
    
    # Per l'edició, necessitem les mateixes dades que a la vista general
    instalacions = Instalacio.objects.all()
    usuaris = User.objects.exclude(username='marti')
    franges = [f"{h:02d}:{m:02d}" for h in range(8, 24) for m in [0, 15, 30, 45]]
    dies_setmana = [(0, 'Dilluns'), (1, 'Dimarts'), (2, 'Dimecres'), (3, 'Dijous'), (4, 'Divendres'), (5, 'Dissabte'), (6, 'Diumenge')]
    
    return render(request, 'reservescorbera/editar_plantilla.html', {
        'item': item,
        'instalacions': instalacions,
        'usuaris': usuaris,
        'franges': franges,
        'dies_setmana': dies_setmana
    })

@login_required
def buidar_plantilla(request):
    if request.user.is_staff:
        # Esborrem absolutament tots els registres de la PlantillaReserva
        PlantillaReserva.objects.all().delete()
        messages.success(request, "S'ha buidat tota la plantilla setmanal rectament.")
    else:
        messages.error(request, "No tens permisos per fer aquesta acció.")
    
    return redirect('gestio_plantilla')

def activitats_extra(request):
    # 1. Si l'usuari envia el formulari (POST)
    if request.method == "POST":
        titol = request.POST.get('titol')
        data = request.POST.get('data')
        inici = request.POST.get('inici')
        final = request.POST.get('final')
        
        # Creem l'activitat a la base de dades
        ActivitatExtra.objects.create(
            titol=titol,
            data=data,
            inici=inici,
            final=final,
            tipus='extra' # Això és el que farà que es vegi daurat
        )
        return redirect('activitats_extra') # Recarreguem per netejar el formulari

    # 2. Si l'usuari només entra a la pàgina (GET)
    activitats = ActivitatExtra.objects.all().order_by('-data')
    return render(request, 'reservescorbera/activitats_extra.html', {'activitats': activitats})


from django.contrib.auth.models import User

@login_required
def meves_reserves(request):
    ara = timezone.now() # Agafem el moment actual
    
    # 1. Reserves de qui està loguejat (NOMÉS FUTURES o EN CURS)
    reserves_usuari = Reserva.objects.filter(
        entitat=request.user,
        final__gte=ara  # Fem servir 'final' perquè si l'activitat encara no ha acabat, surti a la llista
    ).exclude(
        activitat__icontains="CONSERGE:"
    ).order_by('inici')
    
    # 2. Llista d'entitats (excloent tu, staff i conserges)
    # Aquesta part està perfecta tal com la tenies
    totes_entitats = User.objects.exclude(id=request.user.id) \
                             .exclude(username='marti') \
                             .exclude(is_staff=True) \
                             .exclude(is_superuser=True) \
                             .order_by('username')
    
    return render(request, 'reservescorbera/gestionar_reserves.html', {
        'reserves': reserves_usuari,
        'totes_entitats': totes_entitats
    })

@csrf_exempt # Per evitar l'error 403 que et sortia
@login_required
def eliminar_reserva_entitat(request):
    if request.method == "POST":
        reserva_id = request.POST.get('id')
        reserva = get_object_or_404(Reserva, id=reserva_id)
        
        # 1. Guardem les dades abans d'esborrar
        inici_local = timezone.localtime(reserva.inici)
        final_local = timezone.localtime(reserva.final)
        espai_nom = reserva.instalacio.nom
        activitat_nom = reserva.activitat
        
        # 2. Busquem només els usuaris que TINGUIN correu
        # Això evita que el sistema s'encalli si algú no en té
        destinataris = list(User.objects.filter(
            is_active=True
        ).exclude(
            Q(email='') | Q(email__isnull=True) # Exclou buits i nuls
        ).values_list('email', flat=True))

        if destinataris:
            assumpte = f"📢 ANUL·LACIÓ: {espai_nom} - {activitat_nom}"
            cos = (
                f"Hola,\n\nEs comunica que la següent reserva ha estat ANUL·LADA i l'espai torna a estar disponible:\n\n"
                f"📍 Espai: {espai_nom}\n"
                f"📅 Data: {inici_local.strftime('%d/%m/%Y')}\n"
                f"⏰ Hora: {inici_local.strftime('%H:%M')} - {final_local.strftime('%H:%M')}\n"
                f"👤 Entitat que l'ha alliberat: {request.user.username}\n\n"
                f"Aquest és un missatge automàtic enviat a les entitats amb correu registrat."
            )

            try:
                # Fem servir EmailMessage per poder fer servir BCC (Còpia oculta)
                from django.core.mail import EmailMessage
                email = EmailMessage(
                    subject=assumpte,
                    body=cos,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=['esportscorb@gmail.com'], # T'arriba a tu com a confirmació
                    bcc=destinataris,           # Arriba a tots els que sí que tenen mail
                )
                email.send(fail_silently=False)
            except Exception as e:
                # Si falla l'enviament, ho registrem però deixem que la reserva s'esborri
                print(f"Error enviant correu: {e}")

        # 3. Finalment esborrem la reserva de la base de dades
        reserva.delete()
        return JsonResponse({'status': 'ok'})

    return JsonResponse({'status': 'error'}, status=405)


@staff_member_required
def canviar_password_usuari(request, pk):
    if request.method == "POST":
        usuari = get_object_or_404(User, pk=pk)
        # Només permetem canviar-la si NO és un superusuari (per seguretat)
        if not usuari.is_superuser:
            nova_pass = request.POST.get('nova_password')
            usuari.set_password(nova_pass)
            usuari.save()
            messages.success(request, f"S'ha canviat la contrasenya de {usuari.username} correctament.")
        else:
            messages.error(request, "No pots canviar la contrasenya de l'administrador principal.")
            
    return redirect('/gestio-tecnica/') # O la teva ruta de gestió