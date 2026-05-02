from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name
        
    class Meta:
        verbose_name_plural = 'Categories'

class Brand(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

class Product(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)

    buying_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    stock = models.PositiveIntegerField(default=0)
    image = models.ImageField(upload_to='products/', null=True, blank=True)

    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    upsell_products = models.ManyToManyField('self', blank=True, symmetrical=False, help_text="Products frequently bought together")

    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    specifications = models.JSONField(default=dict, blank=True, help_text="Dynamic attributes e.g. {'RAM': '16GB'}")
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True) 

    def __str__(self):
        return self.name

    @property
    def average_rating(self):
        from django.db.models import Avg
        avg = self.reviews.aggregate(Avg('rating'))['rating__avg']
        return round(avg, 1) if avg else 0

    @property
    def review_count(self):
        return self.reviews.count()

    class Meta:
        permissions = [
            ('can_add_product', 'Can add product'),
            ('can_edit_product', 'Can edit product'),
            ('can_delete_product', 'Can delete product'),
            ('can_view_product', 'Can view product'),
            ('can_add_user', 'Can add user'),
            ('can_edit_user', 'Can edit user'),
            ('can_delete_user', 'Can delete user'),
            ("view_stock", "Can view inventory"),
            ("edit_stock", "Can edit stock"),
            ("delete_stock", "Can delete stock"),
             ("view_sales", "Can view sales"),
            ("create_sale", "Can create sale"),
        ]


class Activity(models.Model):
    message = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.message

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'activities'

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    image = models.ImageField(upload_to='profiles/', null=True, blank=True)        


class Invoice(models.Model):
    invoice_number = models.CharField(max_length=50, unique=True, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_profit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=50, default='Cash')

    def save(self, *args, **kwargs):
        # First save to get ID
        if not self.id:
            super().save(*args, **kwargs)

        # Then generate invoice if missing
        if not self.invoice_number:
            self.invoice_number = f"INV-{timezone.now().strftime('%Y%m%d')}-{self.id}"
            super().save(update_fields=['invoice_number'])
        else:
            super().save(*args, **kwargs)

    def __str__(self):
        return self.invoice_number or f"Invoice {self.id}"


class Sale(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items', null=True, blank=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()

    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    buying_price = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    profit = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    invoice_number = models.CharField(max_length=50, blank=True, null=True) # Kept for backward compatibility

    @property
    def total_price(self):
        return (self.quantity * self.selling_price) - self.discount

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.product.name} - {self.quantity} units"

    def save(self, *args, **kwargs):
        # Validate quantity
        if self.quantity <= 0:
            raise ValueError("Quantity must be greater than 0")

        # Validate stock
        # Only deduct stock if it's a new sale record (no id yet)
        is_new = self.pk is None
        if is_new:
            if self.product.stock < self.quantity:
                raise ValueError(f"Not enough stock. Available: {self.product.stock}")

        # Calculate total_amount and profit
        self.total_amount = (self.selling_price * self.quantity) - self.discount
        self.profit = (self.selling_price - self.buying_price) * self.quantity

        # Deduct stock only when creating
        if is_new:
            self.product.stock -= self.quantity
            self.product.save()

        super().save(*args, **kwargs)


class Expense(models.Model):
    CATEGORY_CHOICES = [
        ('rent', 'Rent'),
        ('utilities', 'Utilities'),
        ('salary', 'Salary'),
        ('supplies', 'Supplies'),
        ('transport', 'Transport'),
        ('maintenance', 'Maintenance'),
        ('marketing', 'Marketing'),
        ('other', 'Other'),
    ]

    title = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='other')
    description = models.TextField(blank=True, null=True)
    date = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.title} - Rs {self.amount} ({self.date})"


class Review(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=100)
    email = models.EmailField()
    rating = models.PositiveSmallIntegerField(default=5) # 1 to 5
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('product', 'email') # One review per email per product

    def __str__(self):
        return f"{self.user.username} - {self.product.name} ({self.rating} stars)"


# ==========================================
# ORDER TRACKING SYSTEM
# ==========================================

class Order(models.Model):
    STATUS_PLACED       = 'placed'
    STATUS_CONFIRMED    = 'confirmed'
    STATUS_PROCESSING   = 'processing'
    STATUS_SHIPPED      = 'shipped'
    STATUS_OUT_FOR_DEL  = 'out_for_delivery'
    STATUS_DELIVERED    = 'delivered'
    STATUS_CANCELLED    = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_PLACED,      'Order Placed'),
        (STATUS_CONFIRMED,   'Confirmed'),
        (STATUS_PROCESSING,  'Processing'),
        (STATUS_SHIPPED,     'Shipped'),
        (STATUS_OUT_FOR_DEL, 'Out for Delivery'),
        (STATUS_DELIVERED,   'Delivered'),
        (STATUS_CANCELLED,   'Cancelled'),
    ]

    # Fixed pipeline — cancel is allowed from any non-delivered step
    STATUS_PIPELINE = [
        STATUS_PLACED,
        STATUS_CONFIRMED,
        STATUS_PROCESSING,
        STATUS_SHIPPED,
        STATUS_OUT_FOR_DEL,
        STATUS_DELIVERED,
    ]

    invoice         = models.OneToOneField(Invoice, on_delete=models.CASCADE, related_name='order', null=True, blank=True)
    tracking_id     = models.CharField(max_length=20, unique=True, blank=True)
    status          = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_PLACED)

    customer_name   = models.CharField(max_length=200, blank=True)
    customer_email  = models.EmailField(blank=True)
    customer_phone  = models.CharField(max_length=30, blank=True)
    shipping_address= models.TextField(blank=True)

    courier_name    = models.CharField(max_length=100, blank=True)
    courier_tracking= models.CharField(max_length=100, blank=True)  # External tracking number

    notes           = models.TextField(blank=True)

    placed_at       = models.DateTimeField(auto_now_add=True)
    confirmed_at    = models.DateTimeField(null=True, blank=True)
    processing_at   = models.DateTimeField(null=True, blank=True)
    shipped_at      = models.DateTimeField(null=True, blank=True)
    out_for_delivery_at = models.DateTimeField(null=True, blank=True)
    delivered_at    = models.DateTimeField(null=True, blank=True)
    cancelled_at    = models.DateTimeField(null=True, blank=True)
    updated_at      = models.DateTimeField(auto_now=True)

    estimated_delivery = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-placed_at']

    def save(self, *args, **kwargs):
        if not self.tracking_id:
            import uuid
            uid = uuid.uuid4().hex[:10].upper()
            self.tracking_id = f"TRK-{uid}"
        super().save(*args, **kwargs)

    def advance_status(self):
        """Move to the next step in the pipeline."""
        if self.status == self.STATUS_CANCELLED:
            raise ValueError("Cannot advance a cancelled order.")
        if self.status == self.STATUS_DELIVERED:
            raise ValueError("Order is already delivered.")
        idx = self.STATUS_PIPELINE.index(self.status)
        new_status = self.STATUS_PIPELINE[idx + 1]
        self.set_status(new_status)

    def cancel_and_restock(self, note=''):
        """Cancel the order and return items to stock."""
        if self.status == self.STATUS_CANCELLED:
            return # Already cancelled
            
        from django.db import transaction
        with transaction.atomic():
            self.set_status(self.STATUS_CANCELLED)
            if note:
                latest_log = self.logs.last()
                if latest_log:
                    latest_log.note = note
                    latest_log.save(update_fields=['note'])
            
            # Restock items from the associated invoice
            if self.invoice:
                for sale in self.invoice.items.all():
                    product = sale.product
                    product.stock += sale.quantity
                    product.save()

    def set_status(self, new_status):
        now = timezone.now()
        self.status = new_status
        ts_map = {
            self.STATUS_CONFIRMED:   'confirmed_at',
            self.STATUS_PROCESSING:  'processing_at',
            self.STATUS_SHIPPED:     'shipped_at',
            self.STATUS_OUT_FOR_DEL: 'out_for_delivery_at',
            self.STATUS_DELIVERED:   'delivered_at',
            self.STATUS_CANCELLED:   'cancelled_at',
        }
        field = ts_map.get(new_status)
        if field:
            setattr(self, field, now)
        self.save()
        # Log the event
        OrderStatusLog.objects.create(order=self, status=new_status)

    def get_timeline(self):
        """Return list of timeline steps with status: done / current / pending."""
        steps = []
        for s in self.STATUS_PIPELINE:
            ts_map = {
                self.STATUS_PLACED:      self.placed_at,
                self.STATUS_CONFIRMED:   self.confirmed_at,
                self.STATUS_PROCESSING:  self.processing_at,
                self.STATUS_SHIPPED:     self.shipped_at,
                self.STATUS_OUT_FOR_DEL: self.out_for_delivery_at,
                self.STATUS_DELIVERED:   self.delivered_at,
            }
            if self.status == self.STATUS_CANCELLED:
                if s == self.STATUS_PLACED:
                    state = 'done'
                else:
                    state = 'cancelled'
            elif ts_map.get(s):
                state = 'done' if s != self.status else 'current'
            elif s == self.status:
                state = 'current'
            else:
                state = 'pending'
            steps.append({
                'status': s,
                'label': dict(self.STATUS_CHOICES)[s],
                'state': state,
                'timestamp': ts_map.get(s),
            })
        return steps

    def __str__(self):
        return f"{self.tracking_id} — {self.get_status_display()}"


class OrderStatusLog(models.Model):
    order      = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='logs')
    status     = models.CharField(max_length=30)
    changed_at = models.DateTimeField(auto_now_add=True)
    note       = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['changed_at']

    def __str__(self):
        return f"{self.order.tracking_id} → {self.status} @ {self.changed_at}"