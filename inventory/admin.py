from django.contrib import admin
from .models import Tire, Inventory


@admin.register(Tire)
class TireAdmin(admin.ModelAdmin):
    list_display = (
        'product_code',
        'manufacturer',
        'brand',
        'size_raw',
        'unit_price',
        'set_price',
    )


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = (
        'tire',
        'total_quantity',
        'reserved_quantity',
        'available_stock',
        'reorder_point',
    )
