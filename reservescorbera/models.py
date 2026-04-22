from django.db import models
from django.contrib.auth.models import User

class Instalacio(models.Model):
    nom = models.CharField(max_length=100)
    # Color per al calendari (per defecte el daurat que t'agrada)
    color = models.CharField(max_length=7, default='#d4af37')
    
    # Imatge de la instal·lació
    imatge = models.ImageField(upload_to='instalacions/', null=True, blank=True)
    
    # Horaris d'obertura i tancament (ajuda a validar reserves)
    hora_obertura = models.TimeField(default="08:00")
    hora_tancament = models.TimeField(default="23:00")

    def __str__(self):
        return self.nom

class Reserva(models.Model):
    ESTATS = [
        ('pendent', 'Pendent'),
        ('validada', 'Validada'), # Unifiquem a 'validada' com tenim al views.py
        ('rebutjada', 'Rebutjada'),
    ]
    
    instalacio = models.ForeignKey(Instalacio, on_delete=models.CASCADE, related_name='reserves')
    entitat = models.ForeignKey(User, on_delete=models.CASCADE)
    activitat = models.CharField(max_length=200)
    inici = models.DateTimeField()
    final = models.DateTimeField()
    estat = models.CharField(max_length=10, choices=ESTATS, default='pendent')
    
    # Data de creació per saber quan es va demanar
    creat_el = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.activitat} - {self.instalacio.nom} ({self.entitat.username})"