from django.contrib import admin
from .models import Order, OrderItem, ChatMessage, Cart, CartItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('total_price',)
    fields = ('medicine', 'quantity', 'total_price', 'refill_after_days', 'refill_reminder_date', 'refill_reminder_sent')


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    readonly_fields = ('sender', 'message', 'timestamp', 'is_read')
    can_delete = False
    ordering = ('timestamp',)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'customer', 'seller', 'status', 'get_total_price_display',
        'created_at', 'customer_hidden', 'seller_hidden',
    )
    list_filter = ('status', 'created_at', 'customer_hidden', 'seller_hidden')
    search_fields = (
        'id', 'customer__username', 'customer__email',
        'seller__username', 'seller__agency_name', 'customer_phone',
    )
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'
    inlines = [OrderItemInline, ChatMessageInline]
    list_per_page = 25

    def get_total_price_display(self, obj):
        return f"₹{obj.get_total_price()}"
    get_total_price_display.short_description = 'Total Price'


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'order', 'medicine', 'quantity', 'total_price',
        'refill_after_days', 'refill_reminder_date', 'refill_reminder_sent',
    )
    list_filter = ('refill_reminder_sent', 'refill_after_days')
    search_fields = ('order__id', 'medicine__name')
    autocomplete_fields = ('medicine',)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'sender', 'short_message', 'timestamp', 'is_read')
    list_filter = ('is_read', 'timestamp')
    search_fields = ('order__id', 'sender__username', 'message')
    readonly_fields = ('timestamp',)

    def short_message(self, obj):
        return obj.message[:50] + ('...' if len(obj.message) > 50 else '')
    short_message.short_description = 'Message'


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ('get_item_total_display',)
    fields = ('medicine', 'quantity', 'get_item_total_display')

    def get_item_total_display(self, obj):
        return f"₹{obj.get_item_total()}" if obj.pk else '-'
    get_item_total_display.short_description = 'Item Total'


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'get_cart_total_display', 'created_at', 'item_count')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('created_at',)
    inlines = [CartItemInline]

    def get_cart_total_display(self, obj):
        return f"₹{obj.get_cart_total()}"
    get_cart_total_display.short_description = 'Cart Total'

    def item_count(self, obj):
        return obj.items.count()
    item_count.short_description = 'Items'


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'cart', 'medicine', 'quantity', 'get_item_total_display')
    search_fields = ('cart__user__username', 'medicine__name')
    autocomplete_fields = ('medicine',)

    def get_item_total_display(self, obj):
        return f"₹{obj.get_item_total()}"
    get_item_total_display.short_description = 'Item Total'