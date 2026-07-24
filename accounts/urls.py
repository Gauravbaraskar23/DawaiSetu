from django.urls import path 
from django.contrib.auth import views as auth_views
from accounts.views import signup, CustomLoginView, CustomLogoutView

urlpatterns = [
    path('signup/', signup, name='signup'),
    path('login/', CustomLoginView.as_view(), name='login'),
    path('logout/', CustomLogoutView.as_view(), name='logout'),
    
    # Password reset urls
    path('password-reset/', auth_views.PasswordResetView.as_view(template_name='registration/custom_password_reset.html',
          subject_template_name='registration/password_reset_subject.txt',
          email_template_name='registration/password_reset_email.txt',
          html_email_template_name='registration/custom_password_reset_email.html',
          ),
         name='password_reset'),
    
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='registration/custom_password_reset_done.html'),
         name='password_reset_done'),
    
    path('password-reset-confirm/<uidb64>/<token>/',
         auth_views.PasswordResetConfirmView.as_view(template_name='registration/custom_password_reset_confirm.html'),
         name='password_reset_confirm'),
    
    path('password-reset-complete/',
         auth_views.PasswordResetCompleteView.as_view(template_name='registration/custom_password_reset_complete.html'),
         name='password_reset_complete'),
    
    # T&C and Privacy 
#     path('terms-and-conditions/', terms_conditions, name='terms'),
#     path('privacy-policy/', privacy_policy, name='privacy'),
    
]
