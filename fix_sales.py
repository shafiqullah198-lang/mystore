#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
django.setup()

from accounts.models import Sale
from django.db.models import Sum

# Fix all Sales with zero total_amount
sales_to_fix = Sale.objects.filter(total_amount=0)
count = 0

for sale in sales_to_fix:
    sale.total_amount = (sale.selling_price * sale.quantity) - sale.discount
    sale.profit = (sale.selling_price - sale.buying_price) * sale.quantity
    sale.save()
    count += 1

print(f"✅ Fixed {count} Sales records")

# Verify totals
total = Sale.objects.aggregate(total=Sum('total_amount'))['total']
profit = Sale.objects.aggregate(total=Sum('profit'))['total']
print(f"Total Sales: Rs {total}")
print(f"Total Profit: Rs {profit}")
