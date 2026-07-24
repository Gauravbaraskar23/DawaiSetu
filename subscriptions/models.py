from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
# from accounts.models import User

User = get_user_model()


# Admin ke liye plans bnane ke liye(Monthly, Yearly etc.)
class SubscriptionPlan(models.Model):
    name = models.CharField(max_length=100) # Free, Pro Monthly, Premium Yearly
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    duration_days = models.IntegerField(default=30, help_text="How many days plans you have added (e.g., 30, 90, 180,365)")
    max_medicines = models.IntegerField(default=30, help_text="How many medicines added by seller ?")
    allow_custom_link = models.BooleanField(default=False, help_text="Are they use their personal store?")
    
    # --- Analytics & Operations Features ---
    has_analytics_dashboard = models.BooleanField(default=False, help_text="Provide detailed sales & views analytics?")
    has_stock_alerts = models.BooleanField(default=False, help_text="Send automated low-stock alerts?")
    can_export_data = models.BooleanField(default=False, help_text="Allow exporting orders to Excel/CSV?")
    max_staff_accounts = models.IntegerField(default=0, help_text="How many sub-users can the seller create? (0 for none)")
    has_custom_domain = models.BooleanField(default=False, help_text="Allow custom subdomain masking?")
    
    def __str__(self):
        return f"{self.name} - {self.price}Rs."
    
# Har seller ka active plan yahan save hoga
class UserSubscription(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True)
    
    # Razorpay Payment Tracking
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=255, blank=True, null=True )

    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    def is_valid(self):
        if not self.is_active:
            return False
        if self.end_date and timezone.now() > self.end_date:
            return False
        return True
    
    def __str__(self):
        return f"{self.user.username} - {self.plan.name if self.plan else 'No Plan' }"

class PremiumPlacementPlan(models.Model):
    name = models.CharField(max_length=100, default="Top 6 Premium Partner") 
    price = models.DecimalField(max_digits=10, decimal_places=2, default=999.00)
    duration_days = models.IntegerField(default=30, help_text="Duration for Top 6 placement (e.g., 30 days)")

    def __str__(self):
        return f"{self.name} - ₹{self.price}"


class PremiumPlacementSubscription(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='premium_placement')
    plan = models.ForeignKey(PremiumPlacementPlan, on_delete=models.SET_NULL, null=True)
    
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=255, blank=True, null=True)

    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    def is_valid(self):
        if not self.is_active:
            return False
        if self.end_date and timezone.now() > self.end_date:
            return False
        return True

    def __str__(self):
        return f"{self.user.username} - Top 6 Active"


# 3. NEW: SELLER STORE PROFILE (Trust & Branding)
class StoreProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='store_profile')
    
    # Trust and Verification
    fssai_license_number = models.CharField(max_length=50, blank=True, null=True)
    fssai_document = models.FileField(upload_to='seller_documents/', blank=True, null=True)
    is_verified = models.BooleanField(default=False, help_text="Admin will check this to give the Blue Tick")
    
    # Custom Domain/Subdomain
    custom_subdomain = models.CharField(max_length=50, blank=True, null=True, unique=True, help_text="e.g., 'vermapharmacy' for vermapharmacy.DawaiSetu.com")
    
    # Naye Location Fields
    store_address = models.TextField(blank=True, null=True, help_text="Full address of the medical store")
    city = models.CharField(max_length=100, blank=True, null=True)
    
    # GPS Coordinates (Map par dikhane ya distance nikalne ke liye)
    latitude = models.DecimalField(max_digits=15, decimal_places=10, null=True, blank=True)
    longitude = models.DecimalField(max_digits=15, decimal_places=10, null=True, blank=True)
    
    def __str__(self):
        return f"Store Profile: {self.user.agency_name}"
    


class PromoOffer(models.Model):
    name = models.CharField(max_length=100, help_text="e.g. 'First-Time Seller Offer'")
    discount_percent = models.PositiveIntegerField(help_text="e.g. 30 for 30% off")
    plans = models.ManyToManyField(SubscriptionPlan, blank=True, help_text="Leave empty to apply to All plans")
    first_time_only = models.BooleanField(default=False, help_text="Only show to sellers who never purchased any plan")
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True, help_text="Leave blank for expiry")
    is_active = models.BooleanField(default=True)
    
    def is_valid(self):
        now = timezone.now()
        if not self.is_active:
            return False
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        return True
    
    def applies_to_plan(self, plan):
        if not self.plans.exists():
            return True
        return self.plans.filter(id=plan.id).exists()
    
    def __str__(self):
        return f"{self.name} ({self.discount_percent}% off)"
    
def get_best_offer_for_seller_and_plan(seller, plan):
    """Returns the highest-value valid offer this seller is eligible for on a given plan."""
    has_ever_subscribed = UserSubscription.objects.filter(user=seller).exists()
    best_offer = None
    best_discount = 0
    
    for offer in PromoOffer.objects.filter(is_active=True):
        if not offer.is_valid():
            continue
        if offer.first_time_only and has_ever_subscribed:
            continue
        if not offer.applies_to_plan(plan):
            continue
        if offer.discount_percent > best_discount:
            best_discount = offer.discount_percent
            best_offer = offer
    
    return best_offer

  
    
  