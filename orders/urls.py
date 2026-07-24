from django.urls import path
from .views import place_order, my_orders, order_detail, profile_view, update_profile, add_to_cart, cart_checkout, update_cart_quantity, remove_from_cart, submit_feedback, generate_invoice, order_history, update_order_status, cancel_order, delete_order_history, export_orders_excel, reorder, submit_review, terms_conditions, privacy_policy

urlpatterns = [
    path('', my_orders, name='my_orders'),
    path('place/<slug:slug>/', place_order, name='place_order'),
    path('<int:order_id>/', order_detail, name='order_detail'),
    
    path('history/', order_history, name='order_history'),
    path('update-status/<int:order_id>/', update_order_status, name='update_order_status'),
    path('cancel/<int:order_id>/', cancel_order, name='cancel_order'),
    path('history/delete/<int:order_id>/', delete_order_history, name='delete_history_single'),
    path('history/clear-all/', delete_order_history, name='clear_all_history'),

    path('profile/', profile_view, name='profile_view'),
    path('profile/update/', update_profile, name='update_profile'),
    path('cart/add/<int:medicine_id>/', add_to_cart, name='add_to_cart'),
    path('cart/checkout/', cart_checkout, name='cart_checkout'),
    
    path('cart/remove/<int:item_id>/', remove_from_cart, name='remove_from_cart'),
    path('cart/update/<int:item_id>/', update_cart_quantity, name='update_cart_quantity'),
    path('feedback/submit/', submit_feedback, name='submit_feedback'),
    path('invoice/<int:order_id>/', generate_invoice, name='generate_invoice'),
    
    path('export/', export_orders_excel, name='export_orders_excel'),
    
    path('reorder/<int:order_id>/', reorder, name='reorder_order'),
    path('review/<int:medicine_id>/', submit_review, name='submit_review'),
    
     # T&C and Privacy 
    path('terms-and-conditions/', terms_conditions, name='terms'),
    path('privacy-policy/', privacy_policy, name='privacy'),
        
]

