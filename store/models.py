from django.db import models
from django.utils.text import slugify
from django.conf import settings

# Create your models here.
class Category(models.Model):
    name = models.CharField(max_length=100)
    
    class Meta:
        verbose_name_plural = "Categories"
        
    def __str__(self):
        return self.name
    
class SubCategory(models.Model):
    category = models.ForeignKey(Category, related_name='subcategories', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    
    class Meta:
        verbose_name_plural = "SubCategories"
        
    def __str__(self):
        return f"{self.category.name} > {self.name}"
    
class Manufacturer(models.Model):
    name = models.CharField(max_length=150)
    
    def __str__(self):
        return self.name
    
class Molecule(models.Model):
    name = models.CharField(max_length=150)
    
    def __str__(self):
        return self.name
    

class Medicine(models.Model):
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='medicines', null=True, blank=True)
    
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    subcategory = models.ForeignKey(SubCategory, on_delete=models.SET_NULL, null=True)
    manufacturer = models.ForeignKey(Manufacturer, on_delete=models.CASCADE)
    molecule = models.ForeignKey(Molecule, on_delete=models.SET_NULL, null=True)
    
    product_image = models.ImageField(upload_to='medicines/images/', blank=True, null=True)
    # company = models.CharField(max_length=150)
    composition = models.CharField(max_length=200)
    
    actual_price = models.DecimalField(max_digits=10, decimal_places=2)
    discounted_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    
    description = models.TextField(blank=True)
    stock_available = models.IntegerField(default=0)
    is_available = models.BooleanField(default=True)
    
    
    def save(self, *args, **kwargs):
        # Automatically generate the slug from the name before saving
        if not self.slug:
            self.slug = slugify(self.name)
            
        # Availability ab hamesha stock ke hisaab se automatically decide hoga
        self.is_available = self.stock_available > 0
        super().save(*args, **kwargs)
        
    def __str__(self):
        return self.name
    
    
    
class StoreVisit(models.Model):
    """Tracks each unique visit to a seller's storefront (dedeuplicated pr session per day )"""
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='store_visits')
    session_key = models.CharField(max_length=40)
    visited_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['seller', 'visited_at']),
        ]
    
    def __str__(self):
        return f"Visit to {self.seller.agency_name} on {self.self.visited_at.date()}"


class Review(models.Model):
    medicine = models.ForeignKey(Medicine, on_delete=models.CASCADE, related_name='reviews')
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='medicine_reviews')
    order_item = models.ForeignKey('orders.OrderItem', on_delete=models.SET_NULL, null=True, blank=True)
    rating = models.PositiveSmallIntegerField(choices=[(i, i) for i in range(1, 6)])
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('medicine', 'customer')
        ordering = ['created_at']
        
    def __str__(self):
        return f"{self.customer.username} rated {self.medicine.name} - {self.rating}/5"