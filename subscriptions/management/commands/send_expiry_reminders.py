from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from subscriptions.models import UserSubscription
from notifications.models import Notification

class Command(BaseCommand):
    help = "Sends expiry reminder notifications to sellers whose plan expires in 2-3 days."

    def handle(self, *args, **options):
        today = timezone.now().date()
        target_dates = [today + timedelta(days=2), today + timedelta(days=3)]

        subscriptions = UserSubscription.objects.filter(
            is_active = True,
            end_date__date__in = target_dates,
            plan__isnull=False
        )
        
        sent_count = 0
        
        for sub in subscriptions:
            # Duplicate na jaaye isiliye har din subscription ke liye unique marker link banate h
            marker_link = f"/subscriptions/pricing/?expiry_reminder={sub.id}_{sub.end_date.date()}"
            
            already_sent = Notification.objects.filter(
                recipient=sub.user,
                link=marker_link,
                
            ).exists()
            
            if already_sent:
                continue
            
            days_left = (sub.end_date.date() - today).days
            
            Notification.objects.create(
                recipient=sub.user,
                title="Your Plan is Expiring Soon!",
                message=(
                    f"Your '{sub.plan.name}' plan will expire on "
                    f"{sub.end_date.strftime('%d %b %Y')} "
                    f"Renew now to keep your store features active without interruption."
                ),
                notification_type="System",
                link=marker_link
            )
            
            sent_count += 1
        self.stdout.write(self.style.SUCCESS(f'Sent {sent_count} expiry reminder notification(s).'))