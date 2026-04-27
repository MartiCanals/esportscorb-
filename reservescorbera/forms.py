from django import forms
from django.contrib.auth.models import User

class UserProfileForm(forms.ModelForm):
    # Definim el camp email amb estils de Bootstrap perquè quedi bé a la vista
    email = forms.EmailField(
        label="Correu Electrònic",
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Exemple: marti@corbera.cat'
        })
    )

    class Meta:
        model = User
        fields = ['email']  # Només permetem editar el mail (l'usuari no es toca)

    # Opcional: Validació perquè no puguin posar un correu que ja existeix
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.exclude(pk=self.instance.pk).filter(email=email).exists():
            raise forms.ValidationError("Aquest correu ja està registrat per un altre usuari.")
        return email