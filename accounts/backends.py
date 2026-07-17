# accounts/backends.py
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()


class EmailOrUsernameModelBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        # Grabs the first user matching the typed text as either a username or an email
        user = User.objects.filter(Q(username__iexact=username) | Q(email__iexact=username)).first()

        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
            
        return None
    
# class EmailOrUsernameModelBackend(ModelBackend):
#     def authenticate(self, request, username=None, password=None, **kwargs):
#         try:
#             # Query the database for a user matching the username OR the email
#             # iexact makes it case-insensitive so "Email@Test.com" matches "email@test.com"
#             # user = User.objects.get(Q(username__iexact=username) | Q(email__iexact=username))
#             user = User.objects.filter(Q(username__iexact=username) | Q(email__iexact=username)).first()
#         except User.DoesNotExist:
#             # No user was found with that email or username
#             return None

#         # If a user is found, check if the password matches
#         if user and user.check_password(password) and self.user_can_authenticate(user):
#             return user
            
#         return None