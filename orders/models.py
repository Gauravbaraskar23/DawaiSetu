from django.db import models
from store.models import Medicine
from accounts.models import User, AbstractUser
from store.models import Medicine
from django.conf import settings

class Order(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Processing', 'Processing'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled') 
    ]
    # Secure tracking of who bought it and who is selling it
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='my_orders')
    customer_phone = models.CharField(max_length=15)
   
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_orders')
    delivery_address = models.TextField()
    
    # ORder History ko safely delete (hide) karne ke liye
    customer_hidden = models.BooleanField(default=False)
    seller_hidden = models.BooleanField(default=False)
    
    status = models.CharField(max_length=200, choices=STATUS_CHOICES, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def get_total_price(self):
        return sum(item.total_price for item in self.items.all())
    
    def __str__(self):
        return f"Order #{self.id}"
    
class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    medicine = models.ForeignKey(Medicine, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantity}x {self.medicine.name}"
    
    
class ChatMessage(models.Model):
    # Chat is attached directly to an order so both parties know what they are talking about!
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='chats')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    
    is_read = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['timestamp'] # Always show oldest to newest



class Cart(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cart')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def get_cart_total(self):
        return sum(item.get_item_total() for item in self.items.all())
    
    def __str__(self):
        return f"Cart - {self.user.username}"
    

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    medicine = models.ForeignKey(Medicine, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    
    def get_item_total(self):
        price = self.medicine.discounted_price if self.medicine.discounted_price else self.medicine.actual_price
        return price * self.quantity
    
    def __str__(self):
        return f"{self.quantity} x {self.medicine.name}"
    