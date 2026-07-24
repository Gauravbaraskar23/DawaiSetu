from django.shortcuts import render, redirect, get_object_or_404
import pandas as pd
from django.core.mail import send_mail
from django.conf import settings
from django.http import HttpResponse
from notifications.models import Notification
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from store.models import Medicine, Review
from .models import Order, OrderItem, ChatMessage, Cart, CartItem
from django.contrib import messages
from accounts.models import User
from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta
from subscriptions.models import SubscriptionPlan

# 1. Place an Order
@login_required(login_url='login')
def place_order(request, slug):
    medicine = get_object_or_404(Medicine, slug=slug, is_available=True)
    
    if request.method == 'POST':
        quantity = int(request.POST.get('quantity', 1))
        address = request.POST.get('address')
        phone = request.POST.get('phone')
        refill_days = int(request.POST.get('refill_days', 0) or 0)

        # Calculate price
        price_per_item = medicine.discounted_price if medicine.discounted_price else medicine.actual_price
        total = price_per_item * quantity
        
        # Create main Order Envelope
        order = Order.objects.create(
            customer=request.user,
            seller=medicine.seller,
            delivery_address=address,
            customer_phone=phone
        )
        
        # Attach the specific Medicine as an OrderItem
        order_item = OrderItem.objects.create(
            order=order,
            medicine=medicine,
            quantity=quantity,
            total_price=total
            
        )
        
        # Refill reminder
        if refill_days > 0:
            reminder_offset = max(refill_days - 3, 1)
            order_item.refill_after_days = refill_days
            order_item.refill_reminder_date = (timezone.now() + timedelta(days=reminder_offset)).date()
            order_item.save()
        
        
        # Reduce stock
        medicine.stock_available -= quantity
        medicine.save()
        
        return redirect('order_detail', order_id=order.id)
    
    return render(request, 'orders/place_order.html', {'medicine': medicine})

# Orders List Dashboard
@login_required(login_url='login')
def my_orders(request):
    
    if request.user.is_store_staff:
        # sellers see orders
        seller = request.user.effective_seller
        orders = Order.objects.filter(seller=seller).exclude(status__in=['Completed' , 'Cancelled']).filter(seller_hidden=False).order_by('-created_at')
        # orders = Order.objects.filter(seller=request.user).exclude(status__in=['Completed' , 'Cancelled']).filter(seller_hidden=False).order_by('-created_at')
    else:
        # customers see placed orders
        orders = Order.objects.filter(customer=request.user).exclude(status__in=['Completed' , 'Cancelled']).filter(seller_hidden=False).order_by('-created_at')
    
    can_export = False
    if request.user.is_store_staff:
        seller = request.user.effective_seller
        can_export = seller.effective_plan_features['can_export_data']
        # if hasattr(seller, 'subscription') and seller.subscription.is_valid():
        #     can_export = seller.subscription.plan.can_export_data    
    
    return render(request, 'orders/order_list.html', {
        'orders':orders,
        'can_export': can_export,
        
        })
        
# 3. Order Detail & Chat
@login_required(login_url='login')
def order_detail(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    effective_seller = request.user.effective_seller
    
    # SECURITY WALL: Only the specific buyer and seller can see this
    # if request.user != order.customer and request.user != order.seller:
    if request.user != order.customer and effective_seller != order.seller:
        return HttpResponseForbidden("You do not have permission to view this order.")
    
    # Mark messages as read
    unread_messages = order.chats.exclude(sender=request.user).filter(is_read=False)
    
    unread_messages.update(is_read=True)
    
    if request.method == "POST":
        message_text = request.POST.get('message')
        
        if message_text:
            chat = ChatMessage.objects.create(order=order, sender=request.user, message=message_text)
            
            # AJAX REQUEST CHECK: Agar JS se request aayi h, toh JSON bhejo (No Refresh)
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                # Local time format ko set karna (e.g. 12:45 PM)
                formatted_time = timezone.localtime(chat.timestamp).strftime("%I:%M %p")
                return JsonResponse({
                    'status': 'success',
                    'message': chat.message,
                    'timestamp': formatted_time
                })
            
            # --- Chat notification logic ---
            notify_user = order.seller if request.user == order.customer else order.customer
            Notification.objects.create(
                recipient=notify_user,
                title=" New Message",
                message=f"You have a new message from {request.user.username} regarding Order #{order.id}.",
                notification_type="Chat",
                link=reverse('order_detail', args=[order.id])
            )
            return redirect('order_detail', order_id=order.id)
        
    return render(request, 'orders/order_detail.html', {'order': order})


# 4 Order history
@login_required(login_url='login')
def order_history(request):
    # Sirf Pending aur Processing orders dikhayein
    if request.user.is_store_staff:
        seller = request.user.effective_seller
        orders = Order.objects.filter(seller=seller, status__in=['Completed', 'Cancelled'], seller_hidden=False).order_by('-created_at')
        # orders = Order.objects.filter(seller=request.user, status__in=['Completed', 'Cancelled'], seller_hidden=False).order_by('-created_at')
    else:    
        orders = Order.objects.filter(customer=request.user, status__in=['Completed', 'Cancelled'], customer_hidden=False).order_by('-created_at')
    return render(request, 'orders/order_history.html', {'orders': orders})

# 5 Update Order status
@login_required(login_url='login')
def update_order_status(request, order_id):
    effective_seller = request.user.effective_seller
    order = get_object_or_404(Order, id=order_id, seller=effective_seller)
    # order = get_object_or_404(Order, id=order_id, seller=request.user)
    
    if not request.user.can_manage_orders:
        messages.error(request, "You don't have permission to update order status. Contact your admin.")
        return redirect('order_detail', order_id=order.id)
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in ['Processing', 'Completed']:
            order.status = new_status
            order.save()
            
            messages.success(request, f"Order status updated to {new_status}.")

            # --- Status update check me add karein ---
            if new_status == 'Completed':
                Notification.objects.create(
                    recipient=order.customer,
                    title=" Order Delivered!",
                    message=f"Great news! Your order #{order.id} from {order.seller.agency_name} has been successfully delivered.",
                    notification_type="Order",
                    link=reverse('order_detail', args=[order.id])
                )
    return redirect('order_detail', order_id=order.id)

# 6 Cancel Order
@login_required(login_url='login')
def cancel_order(request, order_id):
    order = get_object_or_404(Order, id=order_id, customer=request.user)
    if request.method == 'POST' :
        order.status = 'Cancelled'
        order.save()
        
        # Stock wapas badhana h kyunki order cancel ho gaya hai
        for item in order.items.all():
            item.medicine.stock_available += item.quantity
            item.medicine.save()
            
        messages.success(request, 'Order cancelled successfully.')
    return redirect('order_detail', order_id=order.id)

# 7 Delete Order History
@login_required(login_url='login')
def delete_order_history(request, order_id=None):
    if order_id:
        # Single order delete (hide)
        order = get_object_or_404(Order, id=order_id)
        if request.user == order.customer: order.customer_hidden = True
        elif request.user.effective_seller == order.seller: order.seller_hidden = True
        # elif request.user == order.seller: order.seller_hidden = True
        order.save()
        messages.success(request, "Order removed from history.")
        
    else:
        # Clear all history
        if request.user.is_store_staff:
            seller = request.user.effective_seller
            Order.objects.filter(seller=seller, status__in=['Completed', 'Cancelled']).update(seller_hidden=True)
            # Order.objects.filter(seller=request.user, status__in=['Completed', 'Cancelled']).update(seller_hidden=True)
        else:    
            Order.objects.filter(customer=request.user, status__in=['Completed', 'Cancelled']).update(customer_hidden=True)
        messages.success(request, "All order history cleared.")
        
    return redirect('order_history')


# Profile & Cart View
@login_required(login_url='login')
def profile_view(request):
    user = request.user
    context = {'user':user}
    
    if user.is_store_staff:
        seller = user.effective_seller
        features = seller.effective_plan_features
        
        # Seller Profile Improvements: Active inventory count aur received orders summary
        context['my_medicines_count'] = Medicine.objects.filter(seller=seller).count()
        context['pending_orders_count'] = Order.objects.filter(seller=seller, status='Pending' ).count()
        context['is_staff_account'] = user.is_staff_member
        
        # context['my_medicines_count'] = Medicine.objects.filter(seller=user).count()
        # context['pending_orders_count'] = Order.objects.filter(seller=user, status='Pending' ).count()
        
        # ===== SUBSCRIPTION / PLAN DATA (seller_dashboard jaisa hi) =====
        allow_custom_link = False
        has_analytics = False
        has_custom_domain = False
        current_plan_name = None
        
        
        context['allow_custom_link'] = features['allow_custom_link']
        context['has_analytics'] = features['has_analytics_dashboard']
        context['has_custom_domain'] = features['has_custom_domain']
        context['active_plan_names'] = seller.active_plan_names
    
    else:
        # Customer Profile Improvements: Get or create cart and items
        cart, created = Cart.objects.get_or_create(user=user)
        context['cart_items'] = cart.items.all().select_related('medicine')
        context['cart_total'] = cart.get_cart_total()
        
    return render(request, 'orders/profile.html', context)

# Update user profile 
@login_required(login_url='login')
def update_profile(request):
    if request.method == 'POST' :
        user = request.user
        
        # Sabhi users ke liye common fields
        user.email = request.POST.get('email', user.email)
        user.phone_number = request.POST.get('phone_number', user.phone_number)
        user.address = request.POST.get('address', user.address)
        user.pincode = request.POST.get('pincode', user.pincode)
        user.pan_no = request.POST.get('pan_no', user.pan_no)
        
        # Sirf sellers ke liye
        if user.is_store_staff:
            user.agency_name = request.POST.get('agency_name', user.agency_name)
            user.gsitn_no = request.POST.get('gstin_no', user.gsitn_no)
            
            # --- NAYA CODE: GPS Location Update Karna (Seedha User model mein) ---
            lat = request.POST.get('latitude')
            lng = request.POST.get('longitude')
            
            if lat and lng:
                try:
                    user.latitude = float(lat)
                    user.longitude = float(lng)
                except ValueError:
                    pass
            # ---------------------------------
            # # --- NAYA CODE (GPS Location Save Karna) ---
            # if hasattr(user, 'store_profile'):
            #     profile = user.store_profile
            #     lat = request.POST.get('latitude')
            #     lng = request.POST.get('longitude')
                
            #     # Agar Latitude aur Longitude aaye hain toh table me save karein
            #     if lat and lng:
            #         try:
            #             profile.latitude = float(lat)
            #             profile.longitude = float(lng)
            #             profile.save()
            #         except ValueError:
            #             pass # Ignore invalid data error
            # ---------------------------------------------
        
        # Profile Image Handle Karein
        if 'profile_image' in request.FILES:
            user.profile_image = request.FILES['profile_image']
            
        user.save()
        messages.success(request, "Your profile is updated successfully!")
        return redirect('profile_view')
    
    return redirect('profile_view')
    

# Add to Cart View
@login_required(login_url='login')
def add_to_cart(request, medicine_id):
    medicine = get_object_or_404(Medicine, id=medicine_id)
    cart, created = Cart.objects.get_or_create(user=request.user)
    
    cart_item, item_created = CartItem.objects.get_or_create(cart=cart, medicine=medicine)
    if not item_created:
        cart_item.quantity += 1
        cart_item.save()
    
    # Agar request JavaScript (AJAX) se aayi hai, toh JSON return karein (No Redirect)
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'status': 'success',
            'message': f'{medicine.name} successfully added to cart!'
        })
    
    
    messages.success(request, f"{medicine.name} added to cart.")
    return redirect(request.META.get('HTTP_REFERER','home'))

# Order all from Cart (Bulk Checkout)
@login_required(login_url='login')
def cart_checkout(request):
    if request.method == 'POST':
        cart = get_object_or_404(Cart, user=request.user)
        cart_items = cart.items.all()
        
        if not cart_items:
            messages.error(request, "Cart is Empty.")
            return redirect('profile_view') 
        
        address = request.POST.get('address', 'Indore, Madhya Pradesh')
        phone = request.POST.get('phone', request.user.phone_number or 'Not Provided')
        refill_days = int(request.POST.get('refill_days', 0) or 0)
        
        
        # Advanced Marketplace Logic: Group items by seller because each seller gets their order separately
        from collections import defaultdict
        items_by_seller = defaultdict(list)
        for item in cart_items:
            items_by_seller[item.medicine.seller].append(item)
            
        # Create separate orders for each seller automatically
        for seller, items in items_by_seller.items():
            order_seller = seller if seller else User.objects.filter(is_superuser=True).first()
            
            order = Order.objects.create(
                customer=request.user,
                seller=order_seller,
                customer_phone=phone,
                delivery_address=address,
                status='Pending'
            )
            
            for item in items:
                order_item = OrderItem.objects.create(
                    order=order,
                    medicine=item.medicine,
                    quantity=item.quantity,
                    total_price=item.get_item_total()
                )
                
                if refill_days > 0:
                    reminder_offset = max(refill_days - 3, 1)
                    order_item.refill_after_days = refill_days
                    order_item.refill_reminder_date = (timezone.now() + timedelta(days=reminder_offset)).date()
                    order_item.save()
                
                
                Notification.objects.create(
                    recipient=order_seller,
                    title=" New Order Received!",
                    message=f"Customer {request.user.username} has placed an order (Order #{order.id}).",
                    notification_type="Order",
                    link=reverse('order_detail', args=[order.id])
                )
                # Stock management
                item.medicine.stock_available -= item.quantity
                item.medicine.save()
                
        # Clear the customer's cart completely after successful checkout
        cart_items.delete()
        
        
        messages.success(request, "Orders is successfully sent.")
        
        
        return redirect('my_orders')
    
    return redirect('profile_view')

# AJAX Ke Through Quantity Update Karne Ke Liye
@login_required(login_url='login')
def update_cart_quantity(request, item_id):
    if request.method == 'POST' and request.headers.get('x-requested-with') == 'XMLHttpRequest':
        cart_item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
        try:
            # Parse new quantity from JSON or form data
            import json
            data = json.loads(request.body)
            new_qty = int(data.get('quantity', 1))
            
            if new_qty > 0 and new_qty <= cart_item.medicine.stock_available:
                cart_item.quantity = new_qty
                cart_item.save()
                
                # Send back the new item total and grand total
                return JsonResponse({
                    'status': 'success',
                    'item_total': cart_item.get_item_total(),
                    'cart_total': cart_item.cart.get_cart_total()
                })
            
            
            else:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Invalid quantity or out of stock.'
                })
                
            
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            })
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request.'})
 
                 
# Cart item remove krne ke liye
@login_required(login_url='login')
def remove_from_cart(request, item_id):
    cart_item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
    cart_item.delete()
    return redirect('profile_view')

# For submit feedback
# @login_required(login_url='login')
# def submit_feedback(request):
#     if request.method == 'POST' and request.headers.get('x-requested-with') == 'XMLHttpRequest':
#         subject = request.POST.get('subject')
#         message = request.POST.get('message')
        
#         # Yahan aap future me email send karne ya database me save karne ka code likh sakte hain.
#         # Example: SupportTicket.objects.create(user=request.user, subject=subject, message=message)
        
#         return JsonResponse({
#             'status': 'success',
#             'message': 'Your feedback has been submitted successfully!'
#         })
        
#     return JsonResponse({
#         'status': 'error',
#         'message': 'Innvalid request'
#     })

@login_required(login_url='login')
def submit_feedback(request):
    if request.method == 'POST' and request.headers.get('x-requested-with') == 'XMLHttpRequest':
        subject = request.POST.get('subject')
        message = request.POST.get('message')
        user = request.user

        # ===== Real-time Email to Support Team =====
        email_subject = f"[DawaiSetu Support] {subject} — from {user.username}"
        email_body = (
            f"New support request received:\n\n"
            f"From: {user.username}\n"
            f"Email: {user.email or 'Not provided'}\n"
            f"Phone: {user.phone_number or 'Not provided'}\n"
            f"Account Type: {'Seller' if user.is_store_staff else 'Customer'}\n"
            f"Subject: {subject}\n\n"
            f"Message:\n{message}\n"
        )

        try:
            send_mail(
                subject=email_subject,
                message=email_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=['meditracksupportcontact@gmail.com'],
                fail_silently=False,
            )
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': 'Could not send your message right now. Please try again or call our support number.'
            })
        # ==============================================

        return JsonResponse({
            'status': 'success',
            'message': 'Your feedback has been submitted successfully!'
        })

    return JsonResponse({
        'status': 'error',
        'message': 'Invalid request'
    })
    
# Generate Invoice
@login_required(login_url='login')
def generate_invoice(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    effective_seller = request.user.effective_seller
    
    # Security: Sirf uss order ka buyer ya seller hi bill dekh sakta hai
    # if request.user != order.customer and request.user != order.seller and not request.user.is_superuser:
    if request.user != order.customer and effective_seller != order.seller and not request.user.is_superuser:
        return HttpResponseForbidden("You have not permission to see this invoice.")
    
    return render(request, 'orders/invoice.html', {'order': order})


@login_required(login_url='login')
def export_orders_excel(request):
    if not request.user.is_store_staff:
        return HttpResponseForbidden("Only sellers can export data.")

    seller = request.user.effective_seller
    can_export = seller.effective_plan_features['can_export_data']
    
    # if hasattr(seller, 'subscription') and seller.subscription.is_valid():
    #     can_export = seller.subscription.plan.can_export_data

    if not can_export:
        messages.error(request, "Please upgrade your plan to export orders/sales data.")
        return redirect('pricing')

    orders = Order.objects.filter(seller=seller).order_by('-created_at')

    rows = []
    for order in orders:
        for item in order.items.all():
            rows.append({
                'Order ID': order.id,
                'Date': timezone.localtime(order.created_at).strftime('%d-%m-%Y %I:%M %p'),
                'Customer': order.customer.username,
                'Customer Phone': order.customer_phone,
                'Medicine': item.medicine.name,
                'Quantity': item.quantity,
                'Item Total (Rs)': float(item.total_price),
                'Order Status': order.status,
                'Delivery Address': order.delivery_address,
            })

    df = pd.DataFrame(rows)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"DawaiSetu_orders_{timezone.now().strftime('%Y%m%d_%H%M')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    df.to_excel(response, index=False, engine='openpyxl')
    return response


@login_required(login_url='login')
def reorder(request, order_id):
    order = get_object_or_404(Order, id=order_id, customer=request.user)
    cart, created = Cart.objects.get_or_create(user=request.user)

    added_items = []
    skipped_items = []

    for item in order.items.all():
        medicine = item.medicine
        if not medicine.is_available or medicine.stock_available <= 0:
            skipped_items.append(medicine.name)
            continue
        
        cart_item, item_created = CartItem.objects.get_or_create(cart=cart, medicine=medicine)
        desired_qty = item.quantity if item_created else cart_item.quantity + item.quantity
        cart_item.quantity = item.quantity = min(desired_qty, medicine.stock_available)
        cart_item.save()
        added_items.append(medicine.name)
        
    if added_items:
        messages.success(request, f"{len(added_items)} item(s) added to your cart from this order.")
        
    if skipped_items:
        messages.success(request, f"Could not re-add (currently out of stock): {', '.join(skipped_items)}")

    return redirect('profile_view')



@login_required(login_url='login')
def submit_review(request, medicine_id):
    if request.method != 'POST':
        return redirect('profile_view') 
    
    medicine = get_object_or_404(Medicine, id=medicine_id)
    rating = request.POST.get('rating')
    comment = request.POST.get('comment', '').strip()
    
    # Verify the customer actually purchased and received this medicine
    purchased_item = OrderItem.objects.filter(
        order__customer=request.user,
        order__status = 'Completed',
        medicine=medicine
    ).first()
    
    if not purchased_item:
        messages.error(request, "You can only review medicines from completed orders.")
        return redirect('order_history')
    
    try:
        rating = int(rating)
        if rating < 1 or rating > 5:
            raise ValueError
    except (TypeError, ValueError):
        messages.error(request, "Please select a valid rating (1-5 stars).")
        return redirect('order_history')
    
    
    Review.objects.update_or_create(
        medicine=medicine,
        customer=request.user,
        defaults={
            'order_item': purchased_item,
            'rating': rating,
            'comment': comment,
        }
    )
    
    messages.success(request, f"Thank you! Your review for {medicine.name} has been submitted.")
    return redirect('order_history')



def terms_conditions(request):
    return render(request, 'partials/profile_terms.html')

def privacy_policy(request):
    return render(request, 'partials/profile_privacy.html')
