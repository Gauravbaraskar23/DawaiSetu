from django import forms
from .models import Medicine, Category


class MedicineForm(forms.ModelForm):
    category =  forms.ModelChoiceField(
        queryset=Category.objects.all().order_by('name'),
        required=False,
        label='Category',
        help_text='Used to organize the subcategory below. You can also type a new category name.'
        
    )
    class Meta:
        model = Medicine
        exclude = ['slug', 'seller', 'composition', 'is_available']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Editing an existing medicine: pre-select its current category
        if self.instance and self.instance.pk and self.instance.subcategory_id and self.instance.subcategory.category_id:
            self.fields['category'].initial = self.instance.subcategory.category_id
            
        # Make sure Category appears right before Subcategory in the template loop
        order = list(self.fields.keys())
        order.remove('category')
        order.insert(order.index('subcategory'), 'category')
        self.order_fields(order)
        


# class MedicineForm(forms.ModelForm):
#     class Meta:
#         model = Medicine
        
#         exclude = ['slug', 'seller']

        

#         widgets = {
#             'description': forms.Textarea(attrs={'rows': 4}),
#         }
