from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import get_user_model
from django import forms 
# This automatically grabs your custom 'accounts.User' model
User = get_user_model() 

class CustomUserCreationForm(UserCreationForm):
    ROLE_CHOICES = [
        ('customer', 'I am a Customer'),
        ('seller', 'I am a Seller/Pharmacy'),
    ]
    role = forms.ChoiceField(choices=ROLE_CHOICES, widget=forms.RadioSelect, initial='customer' )
    agency_name = forms.CharField(max_length=200, required=False, label="Medical/Agency Name")
    
    email = forms.EmailField(required=True)
    
    class Meta(UserCreationForm.Meta):
        model = User
        # We just need the username here; Django handles the passwords automatically
        fields = ('username', 'email', 'role', 'agency_name')
    
    def save(self, commit=True):
        user = super().save(commit=False)
        
        if self.cleaned_data.get('role') == 'seller':
            user.is_store_staff = True
            user.agency_name = self.cleaned_data.get('agency_name')
        
        else:
            user.is_store_staff = False
            user.agency_name = None
        
        if commit:
            user.save()
        return user    
        
    def clean_email(self):
        email = self.cleaned_data.get('email')
        # Check if any other user already has this exact email
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email
    
class CustomLoginForm(AuthenticationForm):
    username = forms.CharField(label='Username or Email', widget=forms.TextInput(attrs={'autofocus': True}))    
