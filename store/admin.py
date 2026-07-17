from django.contrib import admin
from .models import Category, SubCategory, Manufacturer, Molecule, Medicine

@admin.register(Medicine)
class MedicineAdmin(admin.ModelAdmin):
    list_display = ('name', 'manufacturer', 'actual_price', 'stock_available', 'is_available')
    list_filter = ('is_available', 'manufacturer', 'subcategory')
    search_fields = ('name', 'composition', 'description')
    prepopulated_fields = {'slug': ('name',)} # Auto-fills the slug as you type the name

admin.site.register(Category)
admin.site.register(SubCategory)
admin.site.register(Manufacturer)
admin.site.register(Molecule)