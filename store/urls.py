from django.urls import path
from store.views import  landing_page, seller_dashboard, add_medicine, store_home, medicine_detail, edit_medicine, delete_medicine, upload_medicine_image, bulk_upload_medicines, manage_staff, delete_staff, toggle_staff_status, store_analytics, dismiss_welcome_offer


urlpatterns = [
    path('', landing_page, name='landing'),
    
    path('medicines/', store_home, name='home'),
    
    # The individual product page (using the slug)
    path('medicine/<slug:slug>/', medicine_detail, name='medicine_detail'),
    # For Seller dashboard 
    path('dashboard/', seller_dashboard, name='seller_dashboard'),    
    path('dashboard/add/', add_medicine, name='add_medicine'),
    path('dashboard/bulk-upload/', bulk_upload_medicines, name='bulk_upload_medicines'),
    path('dashboard/edit/<slug:slug>/', edit_medicine, name='edit_medicine'),
    path('dashboard/delete/<slug:slug>/', delete_medicine, name='delete_medicine'),
    path('medicine/<slug:slug>/upload-image/', upload_medicine_image, name='upload_medicine_image'),
    # manage staff
    path('staff/', manage_staff, name='manage_staff'),
    path('staff/toggle/<int:staff_id>/', toggle_staff_status, name='toggle_staff_status'),
    path('staff/delete/<int:staff_id>/', delete_staff, name='delete_staff'),

    path('analytics/', store_analytics, name='store_analytics'), 
    path('dismiss-welcome-offer/', dismiss_welcome_offer, name='dismiss_welcome_offer'),

]
