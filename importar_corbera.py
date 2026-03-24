import os
import django
import pandas as pd

# 1. CONFIGURACIÓ DE DJANGO
# Assegura't que 'esportscorb' és el nom de la carpeta on hi ha el settings.py
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'esportscorb.settings')
django.setup()

from reservescorbera.models import Instalacio
from django.contrib.auth.models import User

def importar():
    print("--- Iniciant importació de dades de Corbera ---")

    # 2. IMPORTAR INSTAL·LACIONS
    try:
        df_pistes = pd.read_csv("instalacions.csv", header=None)
        for index, row in df_pistes.iterrows():
            nom_pista = str(row[0]).strip()
            if nom_pista and nom_pista != "nan":
                obj, created = Instalacio.objects.get_or_create(nom=nom_pista)
                if created:
                    print(f"✅ Pista creada: {nom_pista}")
                else:
                    print(f"ℹ️ La pista ja existia: {nom_pista}")
    except Exception as e:
        print(f"❌ Error llegint instalacions.csv: {e}")

    # 3. IMPORTAR ENTITATS
    try:
        df_entitats = pd.read_csv("entitats.csv", header=None)
        for index, row in df_entitats.iterrows():
            nom_real = str(row[0]).strip()
            # L'email sol estar a la columna 5 (índex 4)
            email = str(row[4]).strip() if len(row) > 4 and pd.notna(row[4]) else ""
            
            if nom_real and nom_real != "nan":
                # Creem un username net (sense accents ni espais)
                username = nom_real.lower().replace(" ", "_").replace("à", "a").replace("è", "e").replace("í", "i").replace("ò", "o").replace("ú", "u").replace("ç", "c")
                
                if not User.objects.filter(username=username).exists():
                    User.objects.create_user(
                        username=username,
                        email=email,
                        password='corbera2024'
                    )
                    print(f"👤 Usuari creat: {username}")
                else:
                    print(f"ℹ️ L'usuari ja existeix: {username}")
    except Exception as e:
        print(f"❌ Error llegint entitats.csv: {e}")

    print("--- Procés finalitzat ---")

if __name__ == "__main__":
    importar()