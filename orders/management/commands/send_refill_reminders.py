from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from orders.models import OrderItem
from notifications.models import Notification


class Command(BaseCommand):
    help = 'Sends refill reminder notifications and emails to customers whose medicine is about to run out.'

    def handle(self, *args, **options):
        today = timezone.now().date()

        items_due = OrderItem.objects.filter(
            refill_reminder_date=today,
            refill_reminder_sent=False,
            refill_after_days__gt=0,
        ).select_related('order', 'order__customer', 'medicine')

        sent_count = 0

        for item in items_due:
            customer = item.order.customer
            medicine = item.medicine

            Notification.objects.create(
                recipient=customer,
                title="Time to Reorder!",
                message=f"Your '{medicine.name}' is running low. Reorder now to avoid running out.",
                notification_type="System",
                link=f"/orders/reorder/{item.order.id}/"
            )

            if customer.email:
                try:
                    send_mail(
                        subject=f"Reminder: Time to reorder {medicine.name}",
                        message=(
                            f"Hi {customer.username},\n\n"
                            f"Based on your last order, your '{medicine.name}' should be running low by now.\n"
                            f"Reorder now to make sure you don't run out.\n\n"
                            f"Reorder here: http://127.0.0.1:8000/orders/reorder/{item.order.id}/\n\n"
                            f"- DawaiSetu Team"
                        ),
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[customer.email],
                        fail_silently=True,
                    )
                except Exception:
                    pass

            item.refill_reminder_sent = True
            item.save(update_fields=['refill_reminder_sent'])
            sent_count += 1

        self.stdout.write(self.style.SUCCESS(f'Sent {sent_count} refill reminder(s).'))