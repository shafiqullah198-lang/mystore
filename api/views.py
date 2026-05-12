from rest_framework import viewsets, status, generics, filters
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import action
from django.db import transaction
from django.db.models import Sum, Count, F
from django.utils import timezone
from django.contrib.auth.models import User, Group, Permission
from datetime import timedelta

from accounts.models import (
    Category, Brand, Product, Invoice, Sale, 
    Expense, Order, OrderStatusLog, Activity
)
from .serializers import (
    UserSerializer, GroupSerializer, PermissionSerializer,
    CategorySerializer, BrandSerializer, ProductSerializer,
    InvoiceSerializer, SaleSerializer, OrderSerializer,
    ExpenseSerializer, ActivitySerializer
)
from .permissions import HasModelPermission

# --- AUTH VIEWS ---

class CurrentUserView(APIView):
    def get(self, request):
        serializer = UserSerializer(request.user)
        # Add permissions list to response
        data = serializer.data
        data['permissions'] = list(request.user.get_all_permissions())
        return Response(data)

# --- DASHBOARD VIEWS ---

class DashboardStatsView(APIView):
    def get(self, request):
        today = timezone.now().date()
        start_of_month = today.replace(day=1)
        
        # Revenue and Profit
        total_revenue = Invoice.objects.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        total_profit = Invoice.objects.aggregate(Sum('total_profit'))['total_profit__sum'] or 0
        month_revenue = Invoice.objects.filter(created_at__date__gte=start_of_month).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        
        # Counts
        total_orders = Order.objects.count()
        pending_orders = Order.objects.filter(status='placed').count()
        total_products = Product.objects.count()
        low_stock_count = Product.objects.filter(stock__lt=10).count()
        
        # Recent Activities
        recent_activities = ActivitySerializer(Activity.objects.all()[:5], many=True).data
        
        return Response({
            'stats': {
                'total_revenue': total_revenue,
                'total_profit': total_profit,
                'month_revenue': month_revenue,
                'total_orders': total_orders,
                'pending_orders': pending_orders,
                'total_products': total_products,
                'low_stock_count': low_stock_count,
            },
            'recent_activities': recent_activities
        })

class RevenueChartView(APIView):
    def get(self, request):
        # Last 7 days revenue
        days = []
        revenue_data = []
        for i in range(6, -1, -1):
            date = timezone.now().date() - timedelta(days=i)
            rev = Invoice.objects.filter(created_at__date=date).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
            days.append(date.strftime('%a'))
            revenue_data.append(rev)
        
        return Response({
            'labels': days,
            'data': revenue_data
        })

# --- PRODUCT & INVENTORY VIEWS ---

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    filterset_fields = ['category', 'brand', 'is_active']
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'price', 'stock']

    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        threshold = request.query_params.get('threshold', 10)
        products = self.queryset.filter(stock__lt=threshold)
        serializer = self.get_serializer(products, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def update_stock(self, request, pk=None):
        product = self.get_object()
        quantity = int(request.data.get('quantity', 0))
        product.stock = F('stock') + quantity
        product.save()
        product.refresh_from_db()
        return Response({'status': 'stock updated', 'new_stock': product.stock})

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer

class BrandViewSet(viewsets.ModelViewSet):
    queryset = Brand.objects.all()
    serializer_class = BrandSerializer

# --- POS & SALES VIEWS ---

class CheckoutView(APIView):
    @transaction.atomic
    def post(self, request):
        items = request.data.get('items', [])
        payment_method = request.data.get('payment_method', 'Cash')
        customer_data = request.data.get('customer', {})
        
        if not items:
            return Response({'error': 'No items in cart'}, status=status.HTTP_400_BAD_REQUEST)

        # Create Invoice
        invoice = Invoice.objects.create(
            created_by=request.user,
            payment_method=payment_method
        )

        total_amount = 0
        total_profit = 0
        total_discount = 0

        for item in items:
            product = Product.objects.get(id=item['product_id'])
            qty = int(item['quantity'])
            
            if product.stock < qty:
                raise ValueError(f"Insufficient stock for {product.name}")

            discount = float(item.get('discount', 0))
            sale = Sale.objects.create(
                invoice=invoice,
                product=product,
                quantity=qty,
                selling_price=product.price,
                buying_price=product.buying_price,
                discount=discount,
                created_by=request.user
            )
            total_amount += sale.total_amount
            total_profit += sale.profit
            total_discount += discount

        # Update Invoice totals
        invoice.total_amount = total_amount
        invoice.total_profit = total_profit
        invoice.total_discount = total_discount
        invoice.save()

        # Create Order
        Order.objects.create(
            invoice=invoice,
            customer_name=customer_data.get('name', ''),
            customer_email=customer_data.get('email', ''),
            customer_phone=customer_data.get('phone', ''),
            shipping_address=customer_data.get('address', '')
        )

        Activity.objects.create(message=f"New sale: {invoice.invoice_number} by {request.user.username}")

        serializer = InvoiceSerializer(invoice)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class SaleViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Sale.objects.all()
    serializer_class = SaleSerializer
    filterset_fields = ['product', 'created_by', 'created_at']

class InvoiceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Invoice.objects.all()
    serializer_class = InvoiceSerializer
    filterset_fields = ['payment_method', 'created_by']
    search_fields = ['invoice_number']

# --- ORDER VIEWS ---

class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    filterset_fields = ['status']
    search_fields = ['tracking_id', 'customer_name']

    @action(detail=True, methods=['post'])
    def advance_status(self, request, pk=None):
        order = self.get_object()
        try:
            order.advance_status()
            return Response({'status': 'order advanced', 'new_status': order.status})
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        order = self.get_object()
        note = request.data.get('note', 'Cancelled via Admin API')
        order.cancel_and_restock(note=note)
        return Response({'status': 'order cancelled'})

# --- EXPENSE VIEWS ---

class ExpenseViewSet(viewsets.ModelViewSet):
    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer
    filterset_fields = ['category', 'date']
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

# --- USER & RBAC VIEWS ---

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    search_fields = ['username', 'email']

class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer

class PermissionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    pagination_class = None # Show all permissions for role assignment
