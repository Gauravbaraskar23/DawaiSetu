import razorpay
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from datetime import timedelta
from django.contrib import messages
from .models import SubscriptionPlan, UserSubscription, PremiumPlacementPlan, PremiumPlacementSubscription, get_best_offer_for_seller_and_plan
from django.db import transaction
from notifications.models import Notification


# Razorpay Client setup
client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

def pricing(request):
    # Dono tarah ke plans fetch krna
    plans = SubscriptionPlan.objects.all().order_by('price')
    premium_plans = PremiumPlacementPlan.objects.all().order_by('price')
    
    plan_offers = {}
    if request.user.is_authenticated and request.user.is_store_staff:
        seller = request.user.effective_seller
        for plan in plans:
            offer = get_best_offer_for_seller_and_plan(seller, plan)
            if offer:
                discounted_price = round(float(plan.price) * (100 - offer.discount_percent) / 100, 2)
                plan_offers[plan.id] = {'offer': offer, 'discounted_price': discounted_price}
                
    return render(request, 'subscriptions/pricing.html', {
        'plans':plans,
        'premium_plans' : premium_plans,
        'plan_offers': plan_offers,
        })


@login_required(login_url='login')
def checkout(request, plan_id):
    # Check karna ki customer kaunsa plan le raha hai (Inventory ya Premium)
    plan_type = request.GET.get('type', 'inventory')  # Default is inventory
    
    if plan_type == 'premium':
        plan = get_object_or_404(PremiumPlacementPlan, id=plan_id)

        # Top 6 Slot Availibility Check
        with transaction.atomic():
            active_slots = PremiumPlacementSubscription.objects.select_for_update().filter(
                is_active=True,
                end_date__gte=timezone.now()
            ).exclude(user=request.user).count()
            
            if active_slots >= 6:
                Notification.objects.create(
                    recipient=request.user,
                    title="Premium Placement Unavailable",
                    message="All 6 Premium Placement slots are currently occupied by other pharmicies. Please try again once a slot becomes available, or contact support for a waitlist.",
                    notification_type="System",
                    link="/subscriptions/pricing/"
                )
                messages.error(request, "Sorry, all 6 Premium Slots are currently full. Please try again later when a slot opens up.")
                return redirect('pricing')
    else:
        plan = get_object_or_404(SubscriptionPlan, id=plan_id)
    
    # Agar Free Plan hai (0 rs), toh direct assign kar do
    if plan.price == 0:
        if plan_type == 'premium':
            sub_obj, created = PremiumPlacementSubscription.objects.update_or_create(
            user=request.user,
            defaults={
                'plan': plan,
                'is_active': True,
                'start_date': timezone.now(),
                'end_date': timezone.now() + timedelta(days=plan.duration_days)
                
            }
        )
        
        else:
            sub_obj = UserSubscription.objects.create(
                user=request.user,
                plan=plan,
                is_active=True,
                start_date=timezone.now(),
                end_date=timezone.now() + timedelta(days=plan.duration_days)
                # defaults={
                #     'plan': plan,
                #     'is_active': True,
                #     'start_date': timezone.now(),
                #     'end_date': timezone.now() + timedelta(days=plan.duration_days)
                    
                # }
            )
        
        # Purchase Success Notification
        Notification.objects.create(
            recipient=request.user,
            title="Plan Activated Successfully!",
            message=f"Your '{plan.name}' plan is now active. Valid from {sub_obj.start_date.strftime('%d %b %Y')} to {sub_obj.end_date.strftime('%d %b %Y')}.",
            notification_type="System",
            link="subscriptions/pricing/",
        )
        
        
        messages.success(request, f"You have successfully activated the {plan.name} plan!")
        return redirect('seller_dashboard')
    
    final_price = plan.price
    if plan_type != 'premium':
        seller = request.user.effective_seller
        applied_offer = get_best_offer_for_seller_and_plan(seller, plan)
        if applied_offer:
            final_price = round(float(plan.price) * (100 - applied_offer.discount_percent) / 100, 2)
            
            
    # Paid Plan ke liye Razorpay Order Create karna
    amount = int(final_price * 100) # Razorpay paise me amount leta hai (₹1 = 100 paise)
    # amount = int(plan.price * 100) # Razorpay paise me amount leta hai (₹1 = 100 paise)
    
    payment_data = {
        'amount': amount,
        'currency': 'INR',
        'receipt': f'receipt_{plan_type}_{plan.id}_{request.user.id}',
        'payment_capture': 1 # Auto capture
    }
    
    razorpay_order = client.order.create(data=payment_data)
    
    context = {
        'plan': plan,
        'razorpay_order_id': razorpay_order['id'],
        'razorpay_merchant_key': settings.RAZORPAY_KEY_ID,
        'amount': amount,
        'currency': 'INR'
    }
    return render(request, 'subscriptions/checkout.html', context)


@csrf_exempt
def payment_success(request):
    if request.method == 'POST':
        
        # Razorpay se aaye hue data ko catch karna
        user_id = request.POST.get('user_id')
        payment_id = request.POST.get('razorpay_payment_id', '')
        order_id = request.POST.get('razorpay_order_id', '')
        signature = request.POST.get('razorpay_signature', '')
        plan_id = request.POST.get('plan_id', '')
        plan_type = request.POST.get('plan_type') 
        
        # Agar plan_type blank hai, toh ID check karke identify karo
        if not plan_type or plan_type == '':
            if PremiumPlacementPlan.objects.filter(id=plan_id).exists():
                plan_type = 'premium'
            else:
                plan_type = 'inventory'
        
        # User object fetch kre
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.get(id=user_id)
        
        # Payments verify krna
        params_dict = {
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        }
        
        # DEBUG: Check if we are even receiving the plan_type
        # print(f"DEBUG: Plan Type Received: {plan_type}")
        # print(f"DEBUG: Plan ID Received: {plan_id}")
        
        try:
            with transaction.atomic():
                client.utility.verify_payment_signature(params_dict)
            
            # Signature valid hai, Payment successful! 
            # Ab user ko plan assign kardo
                if  plan_type == 'premium':
                    plan = PremiumPlacementPlan.objects.get(id=plan_id)
                    
                    # DEBUG: Print to check if plan is found
                    # print(f"DEBUG: Found Premium Plan: {plan.name}")
                    
                    # Safety-Net Re-Check (rece condition ke against )
                    active_slots = PremiumPlacementSubscription.objects.filter(
                        is_active=True,
                        end_date__gte=timezone.now(),
                    ).exclude(user=user).count()
                    
                    if active_slots >= 6:
                        Notification.objects.create(
                            recipient=user,
                            title="Premium Placement Slot No Longer Available",
                            message="Unfortunately all Premium slots were taken just before your payment has been recieved - our support team will contact you shortly to process a refund or offer the next available slot.",
                            notification_type="System",
                            link="/subscriptions/pricing/"
                        )
                        messages.error(request, "All Premium slots were filled just before your payment completed. Please contact support team for a refund - we're sorry for the inconvenience.")
                        return redirect('pricing')

                    
                    obj, created = PremiumPlacementSubscription.objects.update_or_create(
                        user=user,
                        defaults={
                            'plan': plan,
                            'razorpay_order_id': order_id,
                            'razorpay_payment_id': payment_id,
                            'razorpay_signature': signature,
                            'is_active': True,
                            'start_date': timezone.now(),
                            'end_date': timezone.now() + timedelta(days=plan.duration_days)
                        }
                    )
                    # print(f"DEBUG: Record Created/Updated: {created}")
                else:
                    plan = SubscriptionPlan.objects.get(id=plan_id)
                    
                    obj = UserSubscription.objects.create(
                        user=user,
                        plan=plan,
                        razorpay_order_id=order_id,
                        razorpay_payment_id=payment_id,
                        razorpay_signature=signature,
                        is_active=True,
                        start_date=timezone.now(),
                        end_date=timezone.now() + timedelta(days=plan.duration_days)
                        # defaults={
                        #     'plan': plan,
                        #     'razorpay_order_id': order_id,
                        #     'razorpay_payment_id': payment_id,
                        #     'razorpay_signature': signature,
                        #     'is_active': True,
                        #     'start_date': timezone.now(),
                        #     'end_date': timezone.now() + timedelta(days=plan.duration_days)
                            
                        # }
                    )
                
                # Purchase Success Notification
                Notification.objects.create(
                    recipient=user,
                    title="Plan Activated Successfully!",
                    message=f"Your '{plan.name}' plan is now active. Valid from {obj.start_date.strftime('%d %b %Y')} to {obj.end_date.strftime('%d %b %Y')}.",
                    notification_type="System",
                    link="/subscriptions/pricing/"
                )
                
                messages.success(request, "Payment Successful! Your subscription is now active.")
                return redirect('seller_dashboard')
        
        except razorpay.errors.SignatureVerificationError:
            messages.error(request, "Payment verification failed. If money was deducted, it will be refunded.")
            return redirect('pricing')
        
    return redirect('pricing')

def plan_detail(request, plan_id):
    plan = get_object_or_404(SubscriptionPlan, id = plan_id)
    today = timezone.now()
    expiry_date = today + timedelta(days=plan.duration_days)
    
    return render(request, 'subscriptions/plan_detail.html', {
        'plan':plan,
        'today': today,
        'expiry_date': expiry_date,
        
    })