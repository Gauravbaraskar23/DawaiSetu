from django.urls import path
from .views import pricing, checkout, payment_success, plan_detail

urlpatterns = [
    path('pricing/', pricing, name='pricing'),
    path('checkout/<int:plan_id>/', checkout, name='checkout'),
    path('payment/success/', payment_success, name='payment_success'),
    path('plan/<int:plan_id>/', plan_detail, name='plan_detail'),
    
]
 