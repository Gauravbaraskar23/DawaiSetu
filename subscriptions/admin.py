from django.contrib import admin
from .models import SubscriptionPlan, UserSubscription, PremiumPlacementPlan, PremiumPlacementSubscription, StoreProfile
 
@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'max_medicines', 'has_analytics_dashboard', 'max_staff_accounts', 'is_verified_plan')
    # list_editable = ('price', 'max_medicines', 'allow_custom_link')
    
    def is_verified_plan(self, obj):
        return "Yes" if obj.price > 0 else "No"
    is_verified_plan.short_description = "Paid Plan"

@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'start_date', 'end_date', 'is_active')
    list_filter = ('is_active', 'plan')
    search_fields = ('user__username', 'razorpay_payment_id')

@admin.register(PremiumPlacementPlan)
class PremiumPlacementPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'duration_days')
    list_editable = ('price', 'duration_days')
    
@admin.register(PremiumPlacementSubscription)
class PremiumPlacementSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'start_date', 'end_date', 'is_active')
    list_filter = ('is_active', 'plan')
 
 
@admin.register(StoreProfile)   
class StoreProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'fssai_license_number', 'is_verified', 'custom_subdomain')
    list_editable = ('is_verified',)
    search_fields = ('user__agency_name', 'fssai_license_number', 'custom_subdomain')