from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = 'Deactivates excess staff accounts for sellers whose plan no longer supports that many staff slots.'

    def handle(self, *args, **options):
        owners = User.objects.filter(is_store_staff=True, parent_seller__isnull=True)
        total_deactivated = 0

        for owner in owners:
            max_staff = owner.effective_plan_features['max_staff_accounts']
            active_staff_qs = owner.staff_members.filter(is_active=True)

            if active_staff_qs.count() > max_staff:
                excess_count = active_staff_qs.count() - max_staff
                excess_ids = list(active_staff_qs.order_by('-date_joined')[:excess_count].values_list('id', flat=True))
                User.objects.filter(id__in=excess_ids).update(is_active=False)
                total_deactivated += excess_count

        self.stdout.write(self.style.SUCCESS(f'Deactivated {total_deactivated} excess staff account(s) across all sellers.'))