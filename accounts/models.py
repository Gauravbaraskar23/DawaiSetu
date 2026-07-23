from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    STAFF_ROLE_CHOICES = (
        ('order_manager', 'Order Manager (Pack & Update Orders)'),
        ('inventory_manager', 'Inventory Manager (Add/Edit Medicines)'),
        ('full_access', 'Full Access (Orders + Inventory)'),
    )
    
    is_customer = models.BooleanField(default=False)
    is_store_staff = models.BooleanField(default=False)
    
    agency_name = models.CharField(max_length=200, blank=True, null=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    
    profile_image = models.ImageField(upload_to='profile_images/', blank=True, null=True)
    shop_id = models.CharField(max_length=50, blank=True, null=True)
    
    # FIX: Added null=True to all new fields
    address = models.TextField(blank=True, null=True)
    pincode = models.CharField(max_length=200, blank=True, null=True)
    gsitn_no = models.CharField(max_length=50, blank=True, null=True)
    pan_no = models.CharField(max_length=20, blank=True, null=True)
    
    # STAFF/ Multi User Feature
    parent_seller = models.ForeignKey(
        'self', on_delete=models.CASCADE, null=True, blank=True,
        related_name='staff_members',
        help_text="Agar ye ek staff sub-account hai, toh iska Admin/Owner kaun hai."
    )
    staff_role = models.CharField(max_length=20, choices=STAFF_ROLE_CHOICES, blank=True, null=True)
    has_dismissed_welcome_offer = models.BooleanField(default=False)
    
    
    def __str__(self):
        return self.username
    
    # Helper Properties
    @property
    def effective_seller(self):
        # Staff account ho toh Admin return karenga, warna khud ko.
        return self.parent_seller if self.parent_seller_id else self

    @property
    def is_staff_member(self):
        return self.parent_seller_id is not None
    
    @property
    def can_manage_inventory(self):
        if not self.is_staff_member:
            return True
        return self.staff_role in ('inventory_manager', 'full_access')
    
    @property
    def can_manage_orders(self):
        if not self.is_staff_member:
            return True
        return self.staff_role in ('order_manager', 'full_access')
    
    
    @property
    def effective_plan_features(self):
        """
        Seller ke saare currently valid plans ko combine karke
        ek merger permission set return krta h.
        Booleans: agar kisi bhi ek plan True h, toh overall True(OR logic)
        Numbers (max_staff_accounts): sabse bada wala plan jitega(MAX logic)
        max_medicines: agar kisi bhi plan mein -1 (Unlimited ) h , toh overall Unlimited
        """
        
        features = {
            'max_medicines': 50,
            'allow_custom_link': False,
            'has_analytics_dashboard': False,
            'has_stock_alerts': False,
            'can_export_data': False,
            'max_staff_accounts': 0,
            'has_custom_domain': False,
        }
        
        valid_subs = [s for s in self.subscriptions.select_related('plan').all() if s.plan and s.is_valid()]
        
        if not valid_subs:
            return features
        
        medicine_limits = []
        for sub in valid_subs:
            plan = sub.plan
            medicine_limits.append(plan.max_medicines)
            features['allow_custom_link'] = features['allow_custom_link'] or plan.allow_custom_link
            features['has_analytics_dashboard'] = features['has_analytics_dashboard'] or plan.has_analytics_dashboard
            features['has_stock_alerts'] = features['has_stock_alerts'] or plan.has_stock_alerts
            features['can_export_data'] = features['can_export_data'] or plan.can_export_data
            features['has_custom_domain'] = features['has_custom_domain'] or plan.has_custom_domain
            features['max_staff_accounts'] = max(features['max_staff_accounts'], plan.max_staff_accounts)

        # features['max_medicines'] = -1 if -1 in medicine_limits else max(medicine_limits)
        if medicine_limits:
            if -1 in medicine_limits:
                features['max_medicines'] = -1
            else:
                # Ignore 0-value add-on plans when calculating the medicine limit,
                # so a staff-only add-on never accidentally zeroes out inventory access
                non_zero_limits = [m for m in medicine_limits if m > 0]
                features['max_medicines'] = max(non_zero_limits) if non_zero_limits else 50
        return features
    
    @property
    def active_plan_names(self):
        # Seller ke saare currently valid plans ke naam, list ke roop mein.
        return [s.plan.name for s in self.subscriptions.select_related('plan').all() if s.plan and s.is_valid()]
    
     