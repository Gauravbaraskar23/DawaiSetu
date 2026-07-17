from django import forms
from .models import Medicine

class MedicineForm(forms.ModelForm):
    class Meta:
        model = Medicine
        
        exclude = ['slug', 'seller']

        

        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }
