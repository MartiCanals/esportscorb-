from django.db import models
from django.contrib.auth.models import User

class Instalacio(models.Model):
    nom = models.CharField(max_length=100)

    def __str__(self):
        return self.nom

class Reserva(models.Model):
    ESTATS = [
        ('pendent', 'Pendent'),
        ('aprovat', 'Aprovat'),
        ('rebutjat', 'Rebutjat'),
    ]
    
    instalacio = models.ForeignKey(Instalacio, on_delete=models.CASCADE)
    entitat = models.ForeignKey(User, on_delete=models.CASCADE)
    activitat = models.CharField(max_length=200)
    inici = models.DateTimeField()
    final = models.DateTimeField()
    estat = models.CharField(max_length=10, choices=ESTATS, default='pendent')

    def __str__(self):
        return f"{self.activitat} - {self.instalacio.nom} ({self.entitat.username})"