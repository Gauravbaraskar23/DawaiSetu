from django.shortcuts import render, get_object_or_404, redirect
import uuid
import math
import re 
import json
import pandas as pd
from .models import Medicine, Category, SubCategory, Manufacturer, Molecule, StoreVisit
from django.db.models import Q
from django.contrib.auth.decorators import login_required, user_passes_test
from .forms import MedicineForm
from django.contrib.auth import get_user_model
from django.utils.text import slugify
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from subscriptions.models import StoreProfile, PromoOffer, UserSubscription
from django.db.models import Sum, Count
from django.db.models.functions import TruncMonth, TruncYear 
import csv
from django.http import HttpResponse, JsonResponse
from orders.models import Order, OrderItem

User = get_user_model()


# Helper function to check limits
def get_seller_limits(user):
    # max_meds = 50  # Default Free plan limit
    # allow_link = False  # Default Free Plan permission
    seller=user.effective_seller
    features = seller.effective_plan_features
    
    return features['max_medicines'], features['allow_custom_link']

    # try:
    #     # Check if user has an active subscription
    #     if hasattr(seller, 'subscription') and seller.subscription.is_valid():
    #         max_meds = seller.subscription.plan.max_medicines
    #         allow_link = seller.subscription.plan.allow_custom_link
            
    #     # if hasattr(user, 'subscription') and user.subscription.is_valid():
    #     #     max_meds = user.subscription.plan.max_medicines
    #     #     allow_link = user.subscription.plan.allow_custom_link
    # except:
    #     pass

    # return max_meds, allow_link

def landing_page(request):
    locked_seller_id = request.session.get('locked_seller_id')
    
    # 1. Sirf un sellers ko nikalna jinke paas "Premium Listing" wala plan hai (Max 6)
    premium_sellers = list(User.objects.filter(
        is_store_staff=True,
        premium_placement__is_active=True,
        premium_placement__end_date__gte=timezone.now()
    ).exclude(agency_name__isnull=True).exclude(agency_name="").order_by('-premium_placement__start_date')[:6])
    
    # 2. LOCKED SELLER SAFETY LOGIC
    # Agar customer kisi specific seller ki link se aaya hai, aur wo seller 
    # in top 6 premium me nahi hai, toh hum usko zabardasti list me add kar 
    # denge taaki uska card UI me dikhe aur customer uski inventory dekh sake.
    if locked_seller_id:
        try:
            locked_seller = User.objects.get(id=locked_seller_id)
            if locked_seller not in premium_sellers:
                premium_sellers.append(locked_seller)
        except User.DoesNotExist:
            pass

    context = {
        'sellers': premium_sellers,
        'locked_seller_id': str(locked_seller_id) if locked_seller_id else None,
    }
    return render(request, 'store/landing.html', context)



def is_seller(user):
    return user.is_authenticated and (user.is_store_staff or user.is_superuser)

@user_passes_test(is_seller, login_url='login')
def seller_dashboard(request):
    
    print("FULL GET:", request.GET)
    print("STATUS:", request.GET.get("status"))
    seller = request.user.effective_seller
    features = seller.effective_plan_features
    
    # Limit fetch karein
    max_meds, allow_link = get_seller_limits(request.user) 
    
    # User ka Storeprofile dhundhein ya naya banayein
    store_profile, created = StoreProfile.objects.get_or_create(user=seller)
    # store_profile, created = StoreProfile.objects.get_or_create(user=request.user)
    
    # FSSAI Verification form submit logic
    if request.method == 'POST' and 'verify_store' in request.POST:
        fssai_no = request.POST.get('fssai_number')
        fssai_doc = request.FILES.get('fssai_document')
        
        if fssai_no and fssai_doc:
            store_profile.fssai_license_number = fssai_no
            store_profile.fssai_document = fssai_doc
            store_profile.save()
            messages.success(request, "Verification documents submitted successfully! Admin will review shortly.")
        else:
            messages.error(request, "Please provide both fssai number and document.")
        return redirect('seller_dashboard')
    
     
    # Analytics & Alerts Logic
    has_analytics = features['has_analytics_dashboard']
    has_stock_alerts = features['has_stock_alerts']
    has_custom_domain = features['has_custom_domain']
    
    # has_analytics = False
    # has_stock_alerts = False
    # has_custom_domain = False  # For custom link for each seller

    # Check krein ki user ke pass active plan hai aur usme features h ya nahi
    # if hasattr(seller, 'subscription') and seller.subscription.is_valid():
    #     has_analytics = seller.subscription.plan.has_analytics_dashboard
    #     has_stock_alerts = seller.subscription.plan.has_stock_alerts
    #     has_custom_domain = seller.subscription.plan.has_custom_domain  # Plan me custom domain on hain ya nahi
    
    # if hasattr(request.user, 'subscription') and request.user.subscription.is_valid():
    #     has_analytics = request.user.subscription.plan.has_analytics_dashboard
    #     has_stock_alerts = request.user.subscription.plan.has_stock_alerts
    #     has_custom_domain = request.user.subscription.plan.has_custom_domain  # Plan me custom domain on hain ya nahi
         
        
    # Data calculations
    low_stock_medicines = [] 
    out_of_stock_count = 0
    total_inventory_value = 0
    
    # Hum saari medicines nikaal lete hain calculations ke liye
    all_seller_meds = Medicine.objects.filter(seller=seller)
    # all_seller_meds = Medicine.objects.filter(seller=request.user)
    
    if has_stock_alerts:
        # Vo medicines jinka stock 10 se kam h (Aap threshold change kr skte hain)
        low_stock_medicines = all_seller_meds.filter(stock_available__lte=10, stock_available__gt=0).order_by('stock_available')
        out_of_stock_count = all_seller_meds.filter(stock_available=0).count()
    
    # Low Stock Preview (dashboard widget)
    low_stock_total_count = low_stock_medicines.count() if has_stock_alerts else 0
    if low_stock_total_count > 10:
        low_stock_preview = low_stock_medicines[:7]
        show_low_stock_view_all = True
    else:
        low_stock_preview = low_stock_medicines
        show_low_stock_view_all = False
        
    # =====================================
      
    
    if has_analytics:
        # Total Inventory Value (stock_available * price)
        # Assuming aaple Medicne models me 'stock' aur 'discounted_price' (ya actual price) h
        for med in all_seller_meds:
            price_to_use = med.discounted_price if med.discounted_price else med.actual_price
            if med.stock_available and price_to_use:
                total_inventory_value += (med.stock_available * price_to_use)
                
    if request.method == 'POST' and 'update_stock' in request.POST:
        med_id = request.POST.get('medicine_id')
        new_stock = request.POST.get('new_stock')
        
        try:
            # Sirf is seller ki dawai update ho isliye seller=request.user lagaya hai (Security)
            med = Medicine.objects.get(id=med_id, seller=seller)
            med.stock_available = int(new_stock)
            med.save()
            messages.success(request, f"Stock updated for {med.name} successfully!")
        except Medicine.DoesNotExist:
            messages.error(request, "Medicine not found or access denied.")
        except ValueError:
            messages.error(request, "Invalid stock value entered.")
            
        return redirect('seller_dashboard')
    
    # Bulk Restock Logic - sab hidden/Out of stock medicines ka stock ek saath update
    if request.method == 'POST' and 'bulk_restock' in request.POST:
        try:
            new_stock_value = int(request.POST.get('bulk_stock_value', 0))
            if new_stock_value < 0:
                raise ValueError
        except (TypeError, ValueError):
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status':'error', 'message': 'Please enter a valid stock quantity (0 or more).'})
            messages.error(request, "Please enter a valid stock quantity (0 or more).")
            return redirect(f"{request.path}?status=hidden")
        
        updated_count = Medicine.objects.filter(
            Q(seller=seller) & (Q(is_available=False) | Q(stock_available__lte=0))
            
        ).update(stock_available=new_stock_value, is_available=(new_stock_value > 0))
        
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'success',
                'message': f'Updated stock for {updated_count} medicine(s) to {new_stock_value} units.',
                'updated_count': updated_count,
            })
        messages.success(request, f"Updated stock for {updated_count} medicine(s) to {new_stock_value} units.")
        return redirect(f"{request.path}?status=hidden")
    
    # Bulk low stock Update - sab low-stock medicines ka stock ek saath badhao
    if request.method == 'POST' and 'bulk_low_stock_update' in request.POST:
        if not has_stock_alerts:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': 'This feature requires the Pro Analytics plan.'})
            messages.error(request, "This feature requires the Pro Analytics plan.")
            return redirect('seller_dashboard')
        
        try:
            new_stock_value = int(request.POST.get('bulk_low_stock_value', 0))
            if new_stock_value < 0:
                raise ValueError
        except (TypeError, ValueError):
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': 'Please enter a valid stock quantity (0 or more).'})
            messages.error(request, "Please enter a valid stock quantity (0 or more).")
            return redirect(f"{request.path}?status=low_stock")
        
        updated_count = Medicine.objects.filter(
            seller=seller, stock_available__gt=0, stock_available__lte=10
        ).update(stock_available=new_stock_value, is_available=(new_stock_value > 0))
        
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'success',
                'message': f'Updated stock for {updated_count} low-stock medicine(s) to {new_stock_value} units.',
            })
            
        messages.success(request, f"Updated stock for {updated_count} low-stock medicine(s) to {new_stock_value} units.")
        return redirect(f"{request.path}?status=low_stock")
    
    
    
    
    # CUSTOM SUBDOMAIN Logic 
    if request.method == 'POST' and 'set_subdomain' in request.POST:
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
        
        if not has_custom_domain:
            msg = "Please upgrade your plan to use the custom domain masking feature."
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': msg})
            messages.error(request, msg)
            return redirect('seller_dashboard')
        
            
        raw_subdomain = request.POST.get('subdomain_name', '').strip().lower()
        new_subdomain = re.sub(r'[^a-zA-Z0-9]', '', raw_subdomain)

        if not new_subdomain:
            msg = "Please enter a valid subdomain name."
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': msg})
            messages.error(request, msg)
            return redirect('seller_dashboard')

        if StoreProfile.objects.filter(custom_subdomain=new_subdomain).exclude(user=seller).exists():
            msg = "This domain is already taken. Please choose another unique name."
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': msg})
            messages.error(request, msg)
            return redirect('seller_dashboard')

        store_profile.custom_subdomain = new_subdomain
        store_profile.save()
        msg = f"Congratulations! Your custom store link is now {new_subdomain}"

        if is_ajax:
            new_link = f"http://{new_subdomain}.localhost:8000"
            return JsonResponse({'status': 'success', 'message': msg, 'new_link': new_link})

        messages.success(request, msg)
        return redirect('seller_dashboard')   
    
        # if has_custom_domain:
        #     raw_subdomain = request.POST.get('subdomain_name', '').strip().lower()

        #     # Ye automatically saare spaces aur special characters hata dega aur lowercase kar dega
        #     new_subdomain = re.sub(r'[^a-zA-Z0-9]', '', raw_subdomain)
            
        #     # Validation: Sirf a-z aur 0-9 allowed hai(no_spaces, no special characters)
        #     if not new_subdomain:
        #         msg = "Please enter a valid subdomain name."
        #         if is_ajax:
        #             return JsonResponse({'status': 'error', 'message': msg})
                
        #         messages.error(request, msg)
        #         return redirect('seller_dashboard')
            
        #     # Check karein ki kisi or ne toh ye naam nhi le liya
        #     # elif StoreProfile.objects.filter(custom_subdomain=new_subdomain).exclude(user=request.user).exists():
        #     elif StoreProfile.objects.filter(custom_subdomain=new_subdomain).exclude(user=seller).exists():
        #         messages.error(request, "This domain is already taken.Please choose another unique name. ")
            
        #     else:
        #         store_profile.custom_subdomain = new_subdomain
        #         store_profile.save()
        #         messages.success(request, f"Congratulations! Your custom store link is now {new_subdomain}")
        
        # else:
        #     messages.error(request, "Please upgrade your plan to use the custom domain masking feature.")
        # return redirect('seller_dashboard')
    


    # GET request se search query aur status nikalna
    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')

    # Seller ki saari medicines fetch karna
    medicines = Medicine.objects.filter(seller=seller).order_by('-id')
    # medicines = Medicine.objects.filter(seller=request.user).order_by('-id')

    # 1. Search logic name or composition me search krna
    if query:
        medicines = medicines.filter(
            Q(name__icontains=query) |
            Q(composition__icontains=query)

        )
    # 2. Status filter logic
    
    if status_filter == 'active':
        # Active wo hai jo available hai aur stock > 0 hai
        medicines = medicines.filter(is_available=True, stock_available__gt=0)
    elif status_filter == 'hidden':
        # Hidden wo hai jo manually unavailable kiya gaya hai ya stock 0 hai
        medicines = medicines.filter(Q(is_available=False) | Q(stock_available__lte=0))
    elif status_filter == 'low_stock' and has_stock_alerts:
        medicines = medicines.filter(stock_available__gt=0, stock_available__lte=10)
    elif status_filter == 'low_stock' and not has_stock_alerts:
        status_filter = ''  # Feature pywalled - siltently treat as "All Medicines"

    print("Status:", status_filter)
    print("Medicines after filter:", medicines.count())
        
        
    show_welcome_offer = False
    welcome_offer = None
    if not request.user.is_staff_member and not seller.has_dismissed_welcome_offer:
        if not UserSubscription.objects.filter(user=seller).exists():
            candidate_offer = PromoOffer.objects.filter(is_active=True, first_time_only=True).first()
            if candidate_offer and candidate_offer.is_valid():
                welcome_offer = candidate_offer
                show_welcome_offer = True
    
    context = {    
        'medicines' : medicines,
        'query' : query,
        'status_filter' : status_filter,
        'total_medicines' : Medicine.objects.filter(seller=seller).count(),
        # 'total_medicines' : Medicine.objects.filter(seller=request.user).count(),
        'allow_custom_link' : allow_link, #Ye HTML ko batayega ki link dikhana hai ya nahi
        'store_profile' : store_profile,
        
        # Analytics variables
        'has_analytics': has_analytics,
        'has_stock_alerts': has_stock_alerts,
        'low_stock_medicines': low_stock_medicines,
        'out_of_stock_count': out_of_stock_count,
        'total_inventory_value': total_inventory_value,
        'active_medicines_count': all_seller_meds.filter(is_available=True).count(),
        # Custom Subdomain
        'has_custom_domain': has_custom_domain,
        
    }
    
    context['show_welcome_offer'] = show_welcome_offer
    context['welcome_offer'] = welcome_offer
    context['low_stock_preview'] = low_stock_preview
    context['show_low_stock_view_all'] = show_low_stock_view_all
    context['low_stock_total_count'] = low_stock_total_count
    context['is_staff_account'] = request.user.is_staff_member
    context['can_manage_inventory'] = request.user.can_manage_inventory
    

    return render(request, 'store/seller_dashboard.html', context)


@user_passes_test(is_seller, login_url='login')
def add_medicine(request):
    if not request.user.can_manage_inventory:
        messages.error(request, "You don't have permission to manage inventory. Contact your admin.")
        return redirect('seller_dashboard')

    seller = request.user.effective_seller
    
    max_meds, _ = get_seller_limits(request.user)
    current_meds = Medicine.objects.filter(seller=seller).count()
    # current_meds = Medicine.objects.filter(seller=request.user).count()
    # Agar max_meds -1 nahi hai (yani limited plan hai), tabhi block karo
    if max_meds != -1:
        if current_meds >= max_meds:
            messages.error(request, f"Plan Limit Reached! You can only add {max_meds} medicines. Please upgrade your plan.")
            return redirect('pricing') # Unko pricing page par bhej dein
    else:
        # Unlimited plan ke liye remaining_slots ko infinity maan lo
        current_meds = float('inf')
                
    if request.method == 'POST':
        
        post_data = request.POST.copy()
        
        # Handle dynamic Manufacturer
        
        
        cat_val = post_data.get('category')
        category_obj = None
        if cat_val:
            if cat_val.isdigit():
                category_obj = Category.objects.filter(id=cat_val).first()
            else:
                category_obj, _ = Category.objects.get_or_create(name=cat_val)
                post_data['category'] = category_obj.id
         
        
        man_val = post_data.get('manufacturer')
        # If the value is text (not a numeric ID), it means they typed a new one
        if man_val and not man_val.isdigit(): 
            new_man, _ = Manufacturer.objects.get_or_create(name=man_val)
            post_data['manufacturer'] = new_man.id
            
        # 2. Handle dynamic Molecule
        mol_val = post_data.get('molecule')
        if mol_val and not mol_val.isdigit():
            new_mol, _ = Molecule.objects.get_or_create(name=mol_val)
            post_data['molecule'] = new_mol.id
            
        # 3. Handle dynamic Subcategory
        sub_val = post_data.get('subcategory')
        if sub_val and not sub_val.isdigit():
            # Use the selected/typed Category instead of always defaulting to "Other"
            # default_cat, _ = Category.objects.get_or_create(name="Other")
            default_cat = category_obj or Category.objects.get_or_create(name="Other")[0]
            new_sub, _ = SubCategory.objects.get_or_create(name=sub_val, category=default_cat)
            post_data['subcategory'] = new_sub.id
            
            
        form = MedicineForm(post_data, request.FILES)
        # form = MedicineForm(request.POST, request.FILES)
        
        if form.is_valid():
            medicine = form.save(commit=False)
            # Attach the seller
            medicine.seller = seller
            # medicine.seller = request.user
            
            if not medicine.composition:
                medicine.composition = medicine.molecule.name if medicine.molecule else "Not Specified"
           
            # Generate a highly unique slug using the name + the seller's ID
            base_slug = slugify(medicine.name)
            medicine.slug = f"{base_slug}-{request.user.id}"
            
            if Medicine.objects.filter(slug=medicine.slug).exists():
                import uuid
                medicine.slug = f"{medicine.slug}-{str(uuid.uuid4())[:4]}"
            
            # save safely
            medicine.save()
            messages.success(request, f"{medicine.name} added successfully!")
            return redirect('seller_dashboard')
        else:
            # If form fails, show errors (Optional but good practice)
            messages.error(request, "Please correct the errors below.")
    else:
        form = MedicineForm()
        
    return render(request, 'store/add_medicine.html', {'form': form})

# @user_passes_test(is_seller, login_url='login')
# def bulk_upload_medicines(request):
#     if request.method == 'POST' and request.FILES.get('excel_file'):
#         excel_file = request.FILES['excel_file']
        
#         try:
#             # File read karna (Supports both CSV and Excel)
#             if excel_file.name.endswith('.csv'):
#                 df = pd.read_csv(excel_file, header=None)
#             else: 
#                 df = pd.read_excel(excel_file, header=None)
            
#             #  Remove empty rows
#             df = df.dropna(how='all')
            
#             # Required columns check krna
#             required_cols = ['name', 'manufacturer', 'actual_price']
            
#             # Convert columns to lowercase for easier matching
#             df.columns = [str(c).strip().lower() for c in df.columns]
            
#             missing_cols = [col for col in required_cols if col not in df.columns]
#             if missing_cols:
#                 messages.error(request, f"Missing required columns: {', '.join(missing_cols)}")
#                 return redirect('bulk_upload_medicines')
            
#             success_count = 0
            
#             # Category 'Other' for missing subcategories
#             default_cat = Category.objects.get_or_create(name="Other")
#             default_sub = SubCategory.objects.get_or_create(name="General", category=default_cat)
            
#             for index, row in df.iterrows():
#                 try:
#                     # 1. Skip if name is empty
#                     if pd.isna(row['name']):
#                         continue
                    
#                     # 2. Get or Create Manufacturer
#                     man_name = str(row['manufacturer']).strip()
#                     manufacturer, _ = Manufacturer.objects.get_or_create(name=man_name)
                    
#                     # 3. Get or Create Molecule 
#                     molecule = None
#                     if 'molecule' in df.columns and not pd.isna(row['molecule']):
#                         mol_name = str(row['molecule']).strip()
#                         molecule, _ = Molecule.objects.get_or_create(name=mol_name)
                    
#                     # 4. Handle Prices (Fallback to 0 if invalid)
#                     try: actual_price = float(row['actual_price'])
#                     except: actual_price = 0.0
                    
#                     try: discounted_price = float(row['discounted_price']) if 'discounted_price' in df.columns and not pd.isna(row['discounted_price']) else actual_price
#                     except: discounted_price = actual_price
                    
#                     # 5.Handle Stock (Fallback to 0 )
#                     try: stock = int(row['stock']) if 'stock' in df.columns and not pd.isna(row['stock']) else 0
#                     except: stock = 0
                    
#                     # 6. Default texts for missing optional fields
#                     composition = str(row['composition']).strip() if 'composition' in df.columns and not pd.isna(row['composition']) else "Not Specified"
#                     description = str(row['description']).strip() if 'description' in df.columns and not pd.isna(row['description']) else f"{row['name']} manufactured by {man_name}."
                    
#                     # 7. Create Slug
#                     base_slug = slugify(str(row['name']))
#                     slug = f"{base_slug}-{request.user.id}-{str(uuid.uuid4())[:4]}"
                    
#                     # 8. Create Medicine
#                     Medicine.objects.create(
#                         seller=request.user,
#                         name=str(row['name']).strip(),
#                         slug=slug,
#                         subcategory=default_sub,
#                         manufacturer=manufacturer,
#                         molecule=molecule,
#                         composition=composition,
#                         actual_price=actual_price,
#                         discounted_price=discounted_price,
#                         description=description,
#                         stock_available=stock,
#                         is_available=(stock > 0)
#                     )
#                     success_count += 1
                    
#                 except Exception as row_e:
#                     # Log individual row error but continue the loop
#                     print(f"Error saving row {index}: {row_e}")
#                     continue
            
#             messages.success(request, f"Successfully uploaded {success_count} medicines to your inventory!")
#             return redirect('seller_dashboard')
                
#         except Exception as e:
#             messages.error(request, f"Error processing file: {str(e)}")
#             return redirect('bulk_upload_medicines')
    
#     return render(request, 'store/bulk_upload.html')
                     
@user_passes_test(is_seller, login_url='login')
def bulk_upload_medicines(request):
    if not request.user.can_manage_inventory:
        messages.error(request, "You don't have permission to manage inventory. Contact your admin.")
        return redirect('seller_dashboard')
    
    seller = request.user.effective_seller 
    
    if request.method == 'POST' and request.FILES.get('excel_file'):
        excel_file = request.FILES['excel_file']
        
        try:
            # 1. Bina headers ke file read karein taaki empty rows ka pata chal sake
            if excel_file.name.endswith('.csv'):
                df = pd.read_csv(excel_file, header=None)
            else: 
                df = pd.read_excel(excel_file, header=None)
            
            # 2. Upar ki saari completely khali rows (empty lines) hata dein
            df = df.dropna(how='all')
            
            if df.empty:
                messages.error(request, "The uploaded file is empty.")
                return redirect('bulk_upload_medicines')
                
            # 3. Jo pehli bhari hui line hai, usko Column Headers bana dein
            df.columns = df.iloc[0]
            df = df[1:] # Header ke baad ka data
            
            # 4. Column names ko clean karein (lowercase aur spaces hatayein)
            df.columns = [str(c).strip().lower().replace('_', ' ') for c in df.columns]
            
            # 5. SMART MAPPING: Agar seller ne alag naam likhe hain, toh unhe match karein
            alias_map = {
                'brand name': 'name',
                'medicine name': 'name',
                'product name': 'name',
                'company': 'manufacturer',
                'mfg': 'manufacturer',
                'mrp': 'actual_price',
                'price': 'actual_price',
                'actual price': 'actual_price',
                'discounted price' : 'discounted_price',
                'sub_cat': 'subcategory',
                'cat': 'category', 
                'packing': 'packaging',
            }
            df = df.rename(columns=alias_map)
            
            # 6. Agar Price Excel me nahi hai, toh error na dein, use 0.0 set kar dein
            if 'actual_price' not in df.columns:
                df['actual_price'] = 0.0
                
            # Ab hum check karenge ki Name aur Manufacturer zaroor ho
            required_cols = ['name', 'manufacturer']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                messages.error(request, f"Missing required columns: {', '.join(missing_cols)}")
                return redirect('bulk_upload_medicines')
            
            # Plan Restriction Logic
            # max_meds, _ = get_seller_limits(request.user)
            # current_meds = Medicine.objects.filter(seller=request.user).count()
            
            max_meds, _ = get_seller_limits(request.user)
            current_meds = Medicine.objects.filter(seller=seller).count()
            
            if max_meds != -1:
                remaining_slots = max_meds - current_meds
                
                if remaining_slots <= 0:
                    messages.error(request, f"Plan Limit Reached! You can only add {max_meds} medicines. Please upgrade your plan.")
                    return redirect('pricing') #Unko pricing pr bhej de
            
            else:
                # Unlimited plan ke liye remaining_slots ko infinity maan lo
                remaining_slots = float('inf')
            
            success_count = 0
            
            # Default Category set karein
            # default_cat, _ = Category.objects.get_or_create(name="Other")
            # default_sub, _ = SubCategory.objects.get_or_create(name="General", category=default_cat)
            
            for index, row in df.iterrows():
                if success_count >= remaining_slots:
                    messages.warning(request, f"Plan limit reached during upload! Only {remaining_slots} medicines were  added.")
                    break  # Agar limit cross ho gayi toh loop rok do
                
                try:
                    # Skip if name is completely empty or NaN
                    if pd.isna(row['name']) or str(row['name']).strip().lower() == 'nan':
                        continue
                    
                    # Manufacturer
                    man_name = str(row['manufacturer']).strip()
                    manufacturer, _ = Manufacturer.objects.get_or_create(name=man_name)
                    
                    # Molecule or agar excel me composition h to molecule me composition add ho jaayega
                    molecule = None
                    mol_source = None
                    if 'molecule' in df.columns and not pd.isna(row['molecule']):
                        mol_source = str(row['molecule']).strip()
                        # mol_name = str(row['molecule']).strip()
                        # molecule, _ = Molecule.objects.get_or_create(name=mol_name)
                    elif 'composition' in df.columns and not pd.isna(row['composition']):
                        mol_source = str(row['composition']).strip()
                        
                    if mol_source:
                        molecule, _ = Molecule.objects.get_or_create(name=mol_source)
                    # Category & Subcategory 
                    category_name = None
                    if 'category' in df.columns and not pd.isna(row['category']):
                        category_name = str(row['category']).strip()
                    
                    if category_name:
                        category_obj, _ = Category.objects.get_or_create(name=category_name)
                    else:
                        category_obj, _ = Category.objects.get_or_create(name='Other')
                    
                    subcategory_name = None
                    if 'subcategory' in df.columns and not pd.isna(row['subcategory']):
                        subcategory_name = str(row['subcategory']).strip()
                        
                    if subcategory_name:
                        subcat_obj, _ = SubCategory.objects.get_or_create(name=subcategory_name, category=category_obj)
                    else:
                        subcat_obj, _ = SubCategory.objects.get_or_create(name="General", category=category_obj)
                    # ===================================


                    # Prices (Fallback to 0)
                    try: actual_price = float(row['actual_price'])
                    except: actual_price = 0.0
                    
                    try: discounted_price = float(row['discounted_price']) if 'discounted_price' in df.columns and not pd.isna(row['discounted_price']) else actual_price
                    except: discounted_price = actual_price
                    
                    # Stock (Fallback to 0)
                    try: stock = int(row['stock']) if 'stock' in df.columns and not pd.isna(row['stock']) else 0
                    except: stock = 0
                    
                    # Composition & Description
                    # composition = str(row['composition']).strip() if 'composition' in df.columns and not pd.isna(row['composition']) else "Not Specified"
                    # description = str(row['description']).strip() if 'description' in df.columns and not pd.isna(row['description']) else f"{row['name']} manufactured by {man_name}."
                    
                    # Composition — molecule se le lo agar khud composition column nahi hai
                    if 'composition' in df.columns and not pd.isna(row['composition']):
                        composition = str(row['composition']).strip()
                    elif molecule:
                        composition = molecule.name
                    else:
                        composition = "Not Specified"

                    # Description — agar packaging bhi h toh usse phle jodo, phir description; warna sirf packaging, ya decriptioon or by default description
                    
                    
                    has_description = 'description' in df.columns and not pd.isna(row['description'])
                    has_packaging = 'packaging' in df.columns and not pd.isna(row['packaging'])
                    
                    if has_description and has_packaging:
                        packaging_val = str(row['packaging']).strip() 
                        description_val = str(row['description']).strip() 
                        description = f"Packaging: {packaging_val}\n{description_val}"
                    elif has_description:
                        description = str(row['description']).strip()
                    elif has_packaging:
                        description = f"Packaging: {str(row['packaging']).strip()}" 
                    else:
                        description = f"{row['name']} manufactured by {man_name}."
                    
                    
                    # Create Slug
                    base_slug = slugify(str(row['name']))
                    slug = f"{base_slug}-{request.user.id}-{str(uuid.uuid4())[:4]}"
                    
                    # Database me save karein
                    Medicine.objects.create(
                        seller=seller,
                        # seller=request.user,
                        name=str(row['name']).strip(),
                        slug=slug,
                        subcategory=subcat_obj,
                        manufacturer=manufacturer,
                        molecule=molecule,
                        composition=composition,
                        actual_price=actual_price,
                        discounted_price=discounted_price,
                        description=description,
                        stock_available=stock,
                        # is_available=(stock > 0)
                    )
                    success_count += 1
                    
                except Exception as row_e:
                    print(f"Error saving row {index}: {row_e}")
                    continue
            
            messages.success(request, f"Successfully uploaded {success_count} medicines to your inventory!")
            return redirect('seller_dashboard')
                
        except Exception as e:
            messages.error(request, f"Error processing file: {str(e)}")
            return redirect('bulk_upload_medicines')
    
    return render(request, 'store/bulk_upload.html')         

@user_passes_test(is_seller, login_url='login')
def edit_medicine(request, slug):
    if not request.user.can_manage_inventory:
        messages.error(request, "You don't have permission to manage inventory. Contact your admin.")
        return redirect('seller_dashboard')
    
    seller = request.user.effective_seller
    
    medicine = get_object_or_404(Medicine, slug=slug , seller=seller)
    # medicine = get_object_or_404(Medicine, slug=slug , seller=request.user)
    
    if request.method == 'POST':
        post_data = request.POST.copy()
        # Handle  DYnamic creation of new manufacturer, Molecule or Subcategory
        
        cat_val = post_data.get('category')
        category_obj = None
        if cat_val:
            if cat_val.isdigit():
                category_obj = Category.objects.filter(id=cat_val).first()
            else:
                category_obj, _ = Category.objects.get_or_create(name=cat_val)
                post_data['category'] = category_obj.id
                
        
        man_val = post_data.get('manufacturer')
        if man_val and not man_val.isdigit():
            new_man, _ = Manufacturer.objects.get_or_create(name=man_val)
            post_data['manufacturer'] = new_man.id

        mol_val = post_data.get('molecule')
        if mol_val and not mol_val.isdigit():
            new_mol, _ = Molecule.objects.get_or_create(name=mol_val)
            post_data['molecule'] = new_mol.id

        sub_val = post_data.get('subcategory')
        if sub_val and not sub_val.isdigit():
            default_cat = category_obj or Category.objects.get_or_create(name="Other")[0]
            new_sub, _ = SubCategory.objects.get_or_create(name=sub_val, category=default_cat)
            post_data['subcategory'] = new_sub.id
        # ================================================================================

        # form = MedicineForm(request.POST, request.FILES, instance=medicine)
        form = MedicineForm(post_data, request.FILES, instance=medicine)
        if form.is_valid():
            # composition ke liye sensible default (kyoki field ab form mein hai hi nahi)
            medicine = form.save(commit=False)
            medicine.seller = seller

            if not medicine.composition:
                medicine.composition = medicine.molecule.name if medicine.molecule else "Not Specified"

            form.save()
            messages.success(request, f"{medicine.name} updated successfully!")
            return redirect('seller_dashboard')
        else:
            messages.error(request, "Please correct the errors below.")
            
    else:
        form = MedicineForm(instance=medicine)
    return render(request, 'store/edit_medicine.html', {'form': form, 'medicine':medicine})

def delete_medicine(request, slug):
    if not request.user.can_manage_inventory:
        messages.error(request, "You don't have permission to manage inventory. Contact your admin.")
        return redirect('seller_dashboard')
    
    seller = request.user.effective_seller
    try:
        medicine = Medicine.objects.get(slug=slug, seller=seller)
        # medicine = Medicine.objects.get(slug=slug, seller=request.user)
    except Medicine.DoesNotExist:
        # If it's already deleted (or doesn't exist), fail gracefully
        return redirect('seller_dashboard')
    
    if request.method == 'POST':
        medicine.delete()
        return redirect('seller_dashboard')
    
    return render(request, 'store/delete_medicine.html', {'medicine': medicine})


# def store_home(request):
    
    
#     # 1. Start with all available medicines
#     medicines = Medicine.objects.filter(is_available=True)
    
#     # 2. Fetch all filter options to display in the sidebar
#     categories = Category.objects.all().prefetch_related('subcategories')
#     manufacturers = Manufacturer.objects.all()
#     molecules = Molecule.objects.all()
    
#     # 3. Fetch all active medical agencies for the sidebar filter
#     sellers = User.objects.filter(is_store_staff=True).exclude(agency_name__isnull=True).exclude(agency_name="")
    
#     # 4. Get user's search and filter inputs from the URL (GET request)
#     query = request.GET.get('q', '')
#     selected_categories = request.GET.getlist('category')
#     selected_subcats = request.GET.getlist('subcategory')
#     selected_manufacturers = request.GET.getlist('manufacturer')
#     selected_molecules = request.GET.getlist('molecule')
    
#     # 5. Capture specific filtered agency ID
#     selected_seller_id = request.GET.get('seller_id', '')
    
#     if selected_seller_id:
#         medicines = medicines.filter(seller_id=selected_seller_id)
    
#     # 6. Apply the Search logic (searches name, composition, or description)
#     if query:
#         medicines = medicines.filter(
#             Q(name__icontains=query) |
#             Q(composition__icontains=query) |
#             Q(description__icontains=query)
#         ).distinct()
        
#     # 7. Apply the Checkbox Filters
#     if selected_categories:
#         medicines = medicines.filter(subcategory__category__id__in=selected_categories)
        
#     if selected_subcats:
#         medicines = medicines.filter(subcategory__id__in=selected_subcats)
        
#     if selected_manufacturers:
#         medicines = medicines.filter(manufacturer__id__in=selected_manufacturers)
        
#     if selected_molecules:
#         medicines = medicines.filter(molecule__id__in=selected_molecules)

#     # 8. Pass everything back to the template
#     context = {
#         'medicines': medicines.distinct(),
#         'categories': categories,
#         'manufacturers': manufacturers,
#         'molecules': molecules,
#         'sellers': sellers,
        
#         # Pass selected values back to keep boxes checked after reload
#         'query': query,
#         'selected_categories': [int(i) for i in selected_categories],
#         'selected_subcats': [int(i) for i in selected_subcats],
#         'selected_manufacturers': [int(i) for i in selected_manufacturers],
#         'selected_molecules': [int(i) for i in selected_molecules],

#         'selected_seller_id': int(selected_seller_id) if selected_seller_id else None,
#     }
    
#     return render(request, 'store/store_home.html', context)


def store_home(request):
    
    # ==========================================
    # NEW CHANGE 1: SESSION LOGIC (Locked Store)
    # ==========================================
    if request.GET.get('locked') == 'true' and request.GET.get('seller_id'):
        request.session['locked_seller_id'] = request.GET.get('seller_id')
        
    # Agar kabhi unlock karna ho toh URL me ?unlock=true bhej kar kar sakte hain
    if request.GET.get('unlock') == 'true' and 'locked_seller_id' in request.session:
        del request.session['locked_seller_id']

    # Session se locked seller ki id nikalein
    locked_seller_id = request.session.get('locked_seller_id')
    # ==========================================

    # 1. Start with all available medicines
    medicines = Medicine.objects.filter(is_available=True)
    
    # 2. Fetch all filter options to display in the sidebar
    categories = Category.objects.all().prefetch_related('subcategories')
    manufacturers = Manufacturer.objects.all()
    molecules = Molecule.objects.all()
    
    # 3. Fetch all active medical agencies for the sidebar filter
    sellers = User.objects.filter(is_store_staff=True).exclude(agency_name__isnull=True).exclude(agency_name="").select_related('store_profile')
    
    # 4. Get user's search and filter inputs from the URL (GET request)
    query = request.GET.get('q', '')
    selected_categories = request.GET.getlist('category')
    selected_subcats = request.GET.getlist('subcategory')
    selected_manufacturers = request.GET.getlist('manufacturer')
    selected_molecules = request.GET.getlist('molecule')
    
    # ==========================================
    # NEW CHANGE 2: AGENCY FILTER OVERRIDE
    # ==========================================
    if locked_seller_id:
        # Agar store locked hai, toh session wala seller id use karein
        selected_seller_id = locked_seller_id
        is_locked = True
    else:
        # Normal user ke liye URL wala seller id use karein
        selected_seller_id = request.GET.get('seller_id', '')
        is_locked = False

    if selected_seller_id:
        medicines = medicines.filter(seller_id=selected_seller_id)
        
    # ==========================================
        
        # Store Visit Tracking (deduplicated per session per day )
        if not request.session.session_key:
            request.session.save()
        session_key = request.session.session_key
        
        today = timezone.now().date()
        already_visited_today = StoreVisit.objects.filter(
            seller_id=selected_seller_id,
            session_key=session_key,
            visited_at__date=today
        ).exists()
        
        if not already_visited_today:
            StoreVisit.objects.create(seller_id=selected_seller_id, session_key=session_key)
            
    # ==========================================

    # 6. Apply the Search logic (searches name, composition, or description)
    if query:
        medicines = medicines.filter(
            Q(name__icontains=query) |
            Q(composition__icontains=query) |
            Q(description__icontains=query)
        ).distinct()
        
    # 7. Apply the Checkbox Filters
    if selected_categories:
        medicines = medicines.filter(subcategory__category__id__in=selected_categories)
        
    if selected_subcats:
        medicines = medicines.filter(subcategory__id__in=selected_subcats)
        
    if selected_manufacturers:
        medicines = medicines.filter(manufacturer__id__in=selected_manufacturers)
        
    if selected_molecules:
        medicines = medicines.filter(molecule__id__in=selected_molecules)

    # 8. Pass everything back to the template
    context = {
        'medicines': medicines.distinct(),
        'categories': categories,
        'manufacturers': manufacturers,
        'molecules': molecules,
        'sellers': sellers,
        
        # Pass selected values back to keep boxes checked after reload
        'query': query,
        'selected_categories': [int(i) for i in selected_categories],
        'selected_subcats': [int(i) for i in selected_subcats],
        'selected_manufacturers': [int(i) for i in selected_manufacturers],
        'selected_molecules': [int(i) for i in selected_molecules],

        'selected_seller_id': int(selected_seller_id) if selected_seller_id else None,
        
       
        'is_locked': is_locked,
    }
    
    return render(request, 'store/store_home.html', context)


def medicine_detail(request, slug):
    # Get the specific medicine using its unique slug, or return a 404 error if not found
    medicine = get_object_or_404(Medicine, slug=slug, is_available=True)
    
    # 1. SELLER / AGENCY FILTER LOGIC
    selected_seller_id = request.GET.get('seller_id', '')
    
    # Average Rating Calculation
    from django.db.models import Avg
    avg_rating = medicine.reviews.aggregate(Avg('rating'))['rating__avg'] or 0
    # ====================================


    if selected_seller_id:
        medicines = medicines.filter(seller_id=selected_seller_id)

    context = {
        'medicine': medicine,
        # 'sellers': User.objects.filter(is_store_staff=True), # Saare sellers bhej rahe hain
        'selected_seller_id': selected_seller_id,
        'avg_rating': avg_rating,
    }
    
    return render(request, 'store/medicine_detail.html', context)

# Upload Medicine Image
@login_required(login_url='login')
def upload_medicine_image(request, slug):
    medicine = get_object_or_404(Medicine, slug=slug)
    effective_seller = request.user.effective_seller
    
    if effective_seller != medicine.seller or not request.user.can_manage_inventory:
        messages.error(request, "You don't have permission to update this medicine's image.")
        return redirect('medicine_detail', slug=slug)
    
    if request.method == 'POST' and request.FILES.get('product_image'):
        medicine.product_image = request.FILES['product_image']
        medicine.save()
        messages.success(request, "Product image uploaded successully!")
    else:
        messages.error(request, "Please select a valid image file.")
    
    return redirect('medicine_detail', slug=slug)

    
@user_passes_test(is_seller, login_url='login')
def manage_staff(request):
    owner = request.user.effective_seller

    # Sirf actual Admin hi staff manage kar sakta hai, koi staff member nahi
    if request.user.is_staff_member:
        messages.error(request, "Only the account owner can manage staff members.")
        return redirect('seller_dashboard')

    max_staff = 0
    # if hasattr(owner, 'subscription') and owner.subscription.is_valid():
    max_staff = owner.effective_plan_features['max_staff_accounts']
        
        # max_staff = owner.subscription.plan.max_staff_accounts

    # Auto Deactivate Excess Staff(plan expire/downgrade hone pr)
    active_staff_qs = owner.staff_members.filter(is_active=True)
    if active_staff_qs.count() > max_staff:
        excess_count = active_staff_qs.count() - max_staff
        # sabse naye add kiye staff pehle deactivate honge
        excess_staff_ids = list(active_staff_qs.order_by('-date_joined')[:excess_count].value_list('id', flat=True))
        User.objects.filter(id__in=excess_staff_ids).update(is_active=False)
        messages.warning(request, f"Your current plan allows only {max_staff} active staff account(s) {excess_count} staff account(s) were automatically deactivated. Upgrade your plan to reactivate them.")
        
    
    staff_members = owner.staff_members.all().order_by('-date_joined')

    if request.method == 'POST':
        if staff_members.count() >= max_staff:
            messages.error(request, f"Your plan allows a maximum of {max_staff} staff accounts. Upgrade your plan to add more.")
            return redirect('manage_staff')

        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        role = request.POST.get('staff_role')

        if not username or not password or not role:
            messages.error(request, "Please fill all fields.")
            return redirect('manage_staff')

        if User.objects.filter(username=username).exists():
            messages.error(request, "This username is already taken.")
            return redirect('manage_staff')

        staff_user = User.objects.create_user(username=username, password=password)
        staff_user.is_store_staff = True
        staff_user.parent_seller = owner
        staff_user.staff_role = role
        staff_user.agency_name = owner.agency_name
        staff_user.save()

        messages.success(request, f"Staff account '{username}' created successfully!")
        return redirect('manage_staff')

    context = {
        'staff_members': staff_members,
        'max_staff': max_staff,
        'remaining_slots': max(0, max_staff - staff_members.count()),
    }
    return render(request, 'store/manage_staff.html', context)


@user_passes_test(is_seller, login_url='login')
def toggle_staff_status(request, staff_id):
    owner = request.user.effective_seller
    staff = get_object_or_404(User, id=staff_id, parent_seller=owner)
    
    if staff.is_active:
        # Deactivate karna hamesha allowed hai
        staff.is_active = False
        staff.save()
        messages.success(request, f"Staff account '{staff.username}' has been deactivated.")
    else:
        # Activate karne se pehle plan limit check karo
        max_staff = owner.effective_plan_features['max_staff_accounts']
        active_count = owner.staff_members.filter(is_active=True).count()

        if active_count >= max_staff:
            messages.error(request, "You cannot activate this staff account because your current plan does not allow more active staff. Please upgrade your plan first.")
        else:
            staff.is_active = True
            staff.save()
            messages.success(request, f"Staff account '{staff.username}' has been activated.")

    # staff.is_active = not staff.is_active
    # staff.save()
    # status_text = "activated" if staff.is_active else "deactivated"
    # messages.success(request, f"Staff account '{staff.username}' has been {status_text}.")
    return redirect('manage_staff')


@user_passes_test(is_seller, login_url='login')
def delete_staff(request, staff_id):
    owner = request.user.effective_seller
    staff = get_object_or_404(User, id=staff_id, parent_seller=owner)
    if request.method == 'POST':
        username = staff.username
        staff.delete()
        messages.success(request, f"Staff account '{username}' removed.")
    return redirect('manage_staff')



# STORE ANALYTICS
@user_passes_test(is_seller, login_url='login')
def store_analytics(request):
    if request.user.is_staff_member:
        messages.error(request, "Only the account owner can view store analytics.")
        return redirect('seller_dashboard')
    
    seller = request.user.effective_seller
    has_analytics = seller.effective_plan_features['has_analytics_dashboard']
    
    if not has_analytics:
        return render(request, 'store/analytics.html', {'has_analytics': False})
    
    now = timezone.now()
    
    # MONTHLY DATA (last 12 Months)
    twelve_month_ago = now - timedelta(days=365)
    
    monthly_visits_qs = (
        StoreVisit.objects.filter(seller=seller, visited_at__gte=twelve_month_ago)
        .annotate(month=TruncMonth('visited_at'))
        .values('month')
        .annotate(count=Count('id'))
        .order_by('month')
    )
    monthly_visits = {v['month'].strftime('%b %Y') : v['count'] for v in monthly_visits_qs}

    monthly_orders_qs = (
        Order.objects.filter(seller=seller, created_at__gte=twelve_month_ago)
        .exclude(status='Cancelled')
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(order_count=Count('id', distinct=True))
        .order_by('month')
    )    
    monthly_orders = {o['month'].strftime('%b %Y'): o['order_count'] for o in monthly_orders_qs}
    
    monthly_sales_qs = (
        OrderItem.objects.filter(order__seller=seller, order__created_at__gte=twelve_month_ago)
        .exclude(order__status='Cancelled')
        .annotate(month=TruncMonth('order__created_at'))
        .values('month')
        .annotate(total=Sum('total_price'))
        .order_by('month')
    )
    monthly_sales = {s['month'].strftime('%b %Y'): float(s['total']) for s in monthly_sales_qs}
    
    # Build a clean chronological list of the last 12 months
    month_labels = []
    visits_series = []
    orders_series = []
    sales_series = []

    
    cursor = now.replace(day=1)
    months_list = []
    for i in range(12):
        months_list.append(cursor.strftime('%b %Y'))
        # Move to previous month
        prev_month = cursor.month -1 or 12
        prev_year = cursor.year -1 if cursor.month == 1 else cursor.year
        cursor = cursor.replace(year=prev_year, month=prev_month, day=1)
    months_list.reverse()
    
    for label in months_list:
        month_labels.append(label)
        visits_series.append(monthly_visits.get(label, 0))
        orders_series.append(monthly_orders.get(label, 0))
        sales_series.append(monthly_sales.get(label, 0))
        
    # ======= YEARLY DATA (Last 5 Years) ========
    five_years_ago = now - timedelta(days=365 * 5)
    
    yearly_visits_qs = (
        StoreVisit.objects.filter(seller=seller, visited_at__gte=five_years_ago)
        .annotate(year=TruncYear('visited_at'))
        .values('year')
        .annotate(count=Count('id'))
        .order_by('year')
    )    
    yearly_visits = {v['year'].year: v['count'] for v in yearly_visits_qs}
    
    yearly_orders_qs = (
        Order.objects.filter(seller=seller, created_at__gte=five_years_ago)
        .exclude(status='Cancelled')
        .annotate(year=TruncYear('created_at'))
        .values('year')
        .annotate(order_count=Count('id', distict=True))
        .order_by('year')
    )
    yearly_orders = {o['year'].year: o['order_count'] for o in yearly_orders_qs}
    
    yearly_sales_qs = (
        OrderItem.objects.filter(order__seller=seller, order__created_at__gte=five_years_ago)
        .exclude(order__status='Cancelled')
        .annotate(year=TruncYear('order__created_at'))
        .values('year')
        .annotate(total=Sum('total_price'))
        .order_by('year')
    )
    yearly_sales = {s['year'].year: float(s['total']) for s in yearly_sales_qs}
    
    current_year = now.year
    year_labels = [str(y) for y in range(current_year -4, current_year + 1)]
    yearly_history = []
    best_year = None
    best_year_sales = -1
    
    for y in range(current_year - 4, current_year + 1):
        year_sales = yearly_sales.get(y, 0)
        year_orders = yearly_orders.get(y, 0)
        year_visits = yearly_visits.get(y, 0)
        avg_order_value = round(year_sales/ year_orders, 2) if year_orders else 0
        
        yearly_history.append({
            'year': y,
            'visits': year_visits,
            'orders': year_orders,
            'sales': year_sales,
            'avg_order_value': avg_order_value,
        })
        
        if year_sales > best_year_sales:
            best_year_sales = year_sales
            best_year = y
            
    # Growth Comparison (this month bs last month)
    this_month_sales = sales_series[-1] if sales_series else 0
    last_month_sales = sales_series[-2] if len(sales_series) >= 2 else 0
    if last_month_sales > 0:
        sales_growth_pct = round(((this_month_sales - last_month_sales) / last_month_sales) * 100, 1)
    else:
        sales_growth_pct = 100 if this_month_sales > 0 else 0    

    total_visits_lifetime = StoreVisit.objects.filter(seller=seller).count()
    total_orders_lifetime = Order.objects.filter(seller=seller).exclude(status='Cancelled').count()
    total_sales_lifetime = OrderItem.objects.filter(order__seller=seller).exclude(order__status='Cancelled').aggregate(total=Sum('total_price'))['total'] or 0
    
    context = {
        'has_analytics': True,
        'month_labels': json.dumps(month_labels),
        'visits_series': json.dumps(visits_series),
        'orders_series': json.dumps(orders_series),
        'sales_series': json.dumps(sales_series),
        'year_labels': json.dumps(year_labels),
        'yearly_history': yearly_history,
        'best_year': best_year,
        'sales_growth_pct': sales_growth_pct,
        'total_visits_lifetime': total_visits_lifetime,
        'total_orders_lifetime': total_orders_lifetime,
        'total_sales_lifetime': total_sales_lifetime,
        'this_month_visits': visits_series[-1] if visits_series else 0,
        'this_month_orders': orders_series[-1] if orders_series else 0,
        'this_month_sales': this_month_sales,
        
    }
    return render(request, 'store/analytics.html', context)


@login_required(login_url='login')
def dismiss_welcome_offer(request):
    if request.method == 'POST':
        seller = request.user.effective_seller
        seller.has_dismissed_welcome_offer = True
        seller.save(update_fields=['has_dismissed_welcome_offer'])
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'})

# Distance nikanlne ka mathematical function (In kilometers)
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371.0 # Earth radius in kilometers
    
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat1)
    log2_rad = math.radians(lon2)
    
    dlon = log2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad
    
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    distance = R * c
    return distance

# View jo aas-pass ke stores dhundhega
def find_nearby_stores(request):
    # Customer ka latitude aur longitude AJAX request se aayega
    user_lat = request.GET.get('lat')
    user_lon = request.GET.get('lng')
    max_distance = float(request.GET.get('radius', 15)) # Default 15 KM ke andar dhundhenge
    
    if not user_lat or not user_lon:
        return JsonResponse({'error': 'Location coordinates missing'}, status=400)
        
    user_lat = float(user_lat)
    user_lon = float(user_lon)
    
    # Un sabhi stores ko fetch karein jinki location database mein hai
    # stores = StoreProfile.objects.filter(latitude__isnull=False, longitude__isnull=False)
    
    # NAYA CHANGE: Seedha User model se active sellers ko filter karein
    sellers = User.objects.filter(is_store_staff=True, latitude__isnull=False, longitude__isnull=False)
    
    nearby_stores = []
    
    # for store in stores:
    #     # Har store ki customer se doori calculate karein
    #     store_lat = float(store.latitude)
    #     store_lon = float(store.longitude)
        
    #     dist = calculate_distance(user_lat, user_lon, store_lat, store_lon)
    for seller in sellers:
        seller_lat = float(seller.latitude)
        seller_lon = float(seller.longitude)
        
        dist = calculate_distance(user_lat, user_lon, seller_lat, seller_lon)   
        approx_road_distance = dist * 1.4
        
        # Agar doori max_distance (jaise 15 km) se kam hai, toh list me add karein
        if approx_road_distance <= max_distance:
            nearby_stores.append({
                'id': seller.id,
                'agency_name': seller.agency_name, # Ya jo bhi aapka store name field ho
                'address': seller.address,
                'city': seller.pincode,
                'distance_km': round(dist, 1), # Doori ko 1 decimal tak round karein (e.g. 2.4 km)
                # 'is_verified': seller.is_verified,
                'distance_km': round(approx_road_distance, 1), # Naya distance bhejein
            })
            
    # List ko sabse nazdeek wale store ke hisaab se sort karein (Kam doori wala sabse upar)
    nearby_stores.sort(key=lambda x: x['distance_km'])
    
    return JsonResponse({'status': 'success', 'stores': nearby_stores})
    