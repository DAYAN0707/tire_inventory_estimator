from django.contrib import admin
from .models import Tire, Inventory

# 管理画面で表示・編集できるよう登録
admin.site.register(Tire)
admin.site.register(Inventory)