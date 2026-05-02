from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from django.contrib import messages

from accounts.models import Activity, Product, Category, Brand, Review, Order, OrderStatusLog, Invoice

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']

@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'brand', 'buying_price', 'price', 'stock', 'created_by', 'is_active', 'created_at']
    fields = ['name', 'category', 'brand', 'description', 'buying_price', 'price', 'stock', 'image', 'upsell_products', 'specifications', 'created_by', 'is_active']
    search_fields = ['name', 'description']
    list_filter = ['is_active', 'category', 'brand']
    filter_horizontal = ['upsell_products']


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ['message', 'created_at']
    search_fields = ['message']
    ordering = ['-created_at']

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['product', 'name', 'email', 'rating', 'created_at']
    list_filter = ['rating', 'created_at']
    search_fields = ['product__name', 'name', 'email', 'comment']


# ==========================================
# ORDER TRACKING ADMIN
# ==========================================

class OrderStatusLogInline(admin.TabularInline):
    model = OrderStatusLog
    extra = 0
    readonly_fields = ['status', 'changed_at', 'note']
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        'tracking_id', 'customer_name', 'status_badge',
        'invoice_link', 'placed_at', 'estimated_delivery', 'updated_at'
    ]
    list_filter  = ['status', 'placed_at', 'courier_name']
    search_fields= ['tracking_id', 'customer_name', 'customer_email', 'customer_phone']
    readonly_fields = ['tracking_id', 'placed_at', 'updated_at',
                       'confirmed_at', 'processing_at', 'shipped_at',
                       'out_for_delivery_at', 'delivered_at', 'cancelled_at']
    inlines      = [OrderStatusLogInline]
    actions      = [
        'action_confirm', 'action_process', 'action_ship',
        'action_out_for_delivery', 'action_deliver', 'action_cancel',
    ]

    fieldsets = (
        ('Tracking', {
            'fields': ('tracking_id', 'status', 'estimated_delivery')
        }),
        ('Customer', {
            'fields': ('customer_name', 'customer_email', 'customer_phone', 'shipping_address')
        }),
        ('Courier', {
            'fields': ('courier_name', 'courier_tracking')
        }),
        ('Invoice', {
            'fields': ('invoice',)
        }),
        ('Timestamps (auto)', {
            'classes': ('collapse',),
            'fields': ('placed_at', 'confirmed_at', 'processing_at',
                       'shipped_at', 'out_for_delivery_at', 'delivered_at',
                       'cancelled_at', 'updated_at'),
        }),
        ('Notes', {'fields': ('notes',)}),
    )

    def status_badge(self, obj):
        colors = {
            'placed':          '#6366f1',
            'confirmed':       '#0ea5e9',
            'processing':      '#f59e0b',
            'shipped':         '#8b5cf6',
            'out_for_delivery':'#f97316',
            'delivered':       '#10b981',
            'cancelled':       '#ef4444',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{};color:white;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def invoice_link(self, obj):
        if obj.invoice:
            return format_html('<a href="/invoice/{}/" target="_blank">{}</a>',
                               obj.invoice.id, obj.invoice.invoice_number)
        return '—'
    invoice_link.short_description = 'Invoice'

    def _bulk_status(self, request, queryset, new_status):
        updated = 0
        errors = []
        for order in queryset:
            try:
                order.set_status(new_status)
                updated += 1
            except ValueError as e:
                errors.append(f"{order.tracking_id}: {e}")
        if updated:
            messages.success(request, f"Updated {updated} order(s) to '{new_status}'.")
        for err in errors:
            messages.error(request, err)

    def action_confirm(self, request, queryset):
        self._bulk_status(request, queryset, Order.STATUS_CONFIRMED)
    action_confirm.short_description = '✅ Mark as Confirmed'

    def action_process(self, request, queryset):
        self._bulk_status(request, queryset, Order.STATUS_PROCESSING)
    action_process.short_description = '⚙️ Mark as Processing'

    def action_ship(self, request, queryset):
        self._bulk_status(request, queryset, Order.STATUS_SHIPPED)
    action_ship.short_description = '📦 Mark as Shipped'

    def action_out_for_delivery(self, request, queryset):
        self._bulk_status(request, queryset, Order.STATUS_OUT_FOR_DEL)
    action_out_for_delivery.short_description = '🛵 Mark as Out for Delivery'

    def action_deliver(self, request, queryset):
        self._bulk_status(request, queryset, Order.STATUS_DELIVERED)
    action_deliver.short_description = '🏠 Mark as Delivered'

    def action_cancel(self, request, queryset):
        self._bulk_status(request, queryset, Order.STATUS_CANCELLED)
    action_cancel.short_description = '❌ Cancel Orders'


@admin.register(OrderStatusLog)
class OrderStatusLogAdmin(admin.ModelAdmin):
    list_display = ['order', 'status', 'changed_at', 'note']
    list_filter  = ['status', 'changed_at']
    search_fields= ['order__tracking_id']
    readonly_fields = ['order', 'status', 'changed_at']
