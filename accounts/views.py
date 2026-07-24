from django.shortcuts import render, redirect
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth import login, logout
from django.urls import reverse_lazy
from .forms import CustomUserCreationForm , CustomLoginForm
from django.contrib import messages


def signup(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            
            messages.success(request, "Account created successfully! Please log in.")
            
            return redirect('login')
    else:
        form = CustomUserCreationForm()
    return render(request, 'registration/signup.html', {'form': form})

class CustomLoginView(LoginView):
    template_name = 'registration/login.html'
    redirect_authenticated_user = True # Prevents already logged-in users from seeing the login page
    authentication_form = CustomLoginForm
    
    
    def form_valid(self,form):
        username = form.get_user().username
        messages.success(self.request, f'Login successful! Welcome back, {username}.')
        return super().form_valid(form)
    
    
    def get_success_url(self):
        """
        Smart redirect: Routes users based on their account role.
        """
        user = self.request.user
        if user.is_store_staff or user.is_superuser:
            return '/dashboard/'  # Store owners go directly to the management dashboard
        return '/'            # Customers go to the main store catalog

class CustomLogoutView(LogoutView):
    # Safely redirects the user back to the login page after they sign out
    next_page = reverse_lazy('login')
    
    

# def terms_conditions(request):
#     return render(request, 'partials/profile_terms.html')

# def privacy_policy(request):
#     return render(request, 'partials/profile_privacy.html')
