# import csv
# import os
# import django

# Setup Django environment
# os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'meditrack.settings')
# django.setup()

# from store.models import Category, SubCategory, Manufacturer, Molecule, Medicine
# from django.utils.text import slugify

# # NOTE: Change this if you named the file something else!
# file_path = "medicines.csv" 

# def clean_str(val):
#     if not val:
#         return "Unknown"
#     return str(val).strip()

# print(f"Starting to read {file_path}...")

# try:
#     with open(file_path, mode='r', encoding='utf-8-sig') as f:
#         # DictReader automatically uses the first row as headers!
#         reader = csv.DictReader(f)
#         count = 0
        
#         for row in reader:
#             brand_name = clean_str(row.get('BRAND_NAME', ''))
#             if not brand_name or brand_name == "Unknown":
#                 continue
                
#             # Extract models using the exact headers from our new CSV
#             company_name = clean_str(row.get('COMPANY', ''))
#             manufacturer, _ = Manufacturer.objects.get_or_create(name=company_name)
            
#             composition_name = clean_str(row.get('COMPOSITION', ''))
#             molecule, _ = Molecule.objects.get_or_create(name=composition_name[:150])
            
#             cat_name = clean_str(row.get('CATEGORY', ''))
#             category, _ = Category.objects.get_or_create(name=cat_name)
            
#             subcat_name = clean_str(row.get('SUBCATEGORY', f"General {cat_name}"))
#             subcategory, _ = SubCategory.objects.get_or_create(category=category, name=subcat_name)

#             # Extract our new pricing and stock data
#             actual_price = float(row.get('ACTUAL_PRICE', 100.0))
#             discounted_price = float(row.get('DISCOUNTED_PRICE', 90.0))
#             stock = int(row.get('STOCK', 50))
#             description = clean_str(row.get('DESCRIPTION', ''))

#             # Save the Medicine
#             base_slug = slugify(brand_name)
#             medicine, created = Medicine.objects.get_or_create(
#                 name=brand_name,
#                 defaults={
#                     'slug': base_slug,
#                     'subcategory': subcategory,
#                     'manufacturer': manufacturer,
#                     'molecule': molecule,
#                     'composition': composition_name[:200],
#                     'actual_price': actual_price,
#                     'discounted_price': discounted_price,
#                     'description': description,
#                     'stock_available': stock,
#                     'is_available': True
#                 }
#             )
            
#             if created:
#                 print(f"Added: {brand_name}")
#                 count += 1
#             else:
#                 print(f"Skipped (already exists): {brand_name}")

#         print(f"\n--- SUCCESS! Imported {count} new medicines! ---")

# except FileNotFoundError:
#     print(f"Error: Could not find '{file_path}'. Make sure the file name matches exactly.")