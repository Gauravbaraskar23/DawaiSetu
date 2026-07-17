from django.urls import path
from .views import get_notifications, mark_notification_read, clear_all_notifications

urlpatterns = [
    path('api/get/', get_notifications, name='get_notifications'),
    path('api/read/<int:notif_id>/', mark_notification_read, name='mark_notification_read'),
    path('api/clear-all/', clear_all_notifications, name='clear_all_notifications'),
    
]
