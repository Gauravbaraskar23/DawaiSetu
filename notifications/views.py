from django.shortcuts import render
from django.http import JsonResponse
from .models import Notification
from django.contrib.auth.decorators import login_required

@login_required(login_url='login')
def get_notifications(request):
    notifs = Notification.objects.filter(recipient=request.user, is_read=False)[:5]
    count = Notification.objects.filter(recipient=request.user, is_read=False).count()
    
    data = []
    for n in notifs:
        data.append({
            'id': n.id,
            'title': n.title,
            'message': n.message,
            'link': n.link,
            'time': n.created_at.strftime("%b %d, %I:%M %p")
            
        })
    return JsonResponse({'count': count, 'notifications': data})


def mark_notification_read(request, notif_id):
    if request.method == 'POST':
        Notification.objects.filter(id=notif_id, recipient=request.user).update(is_read=True)
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'})

@login_required(login_url='login')
def clear_all_notifications(request):
    if request.method == 'POST':
        Notification.objects.filter(recipient=request.user).delete()
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'})
