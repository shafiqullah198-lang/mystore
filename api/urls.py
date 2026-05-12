from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenBlacklistView,
)
from .views import (
    CurrentUserView, DashboardStatsView, RevenueChartView, OrderStatsView,
    ProductViewSet, CategoryViewSet, BrandViewSet,
    CheckoutView, SaleViewSet, InvoiceViewSet,
    OrderViewSet, ExpenseViewSet,
    UserViewSet, GroupViewSet, PermissionViewSet
)

router = DefaultRouter()
router.register(r'products', ProductViewSet)
router.register(r'categories', CategoryViewSet)
router.register(r'brands', BrandViewSet)
router.register(r'sales', SaleViewSet)
router.register(r'invoices', InvoiceViewSet)
router.register(r'orders', OrderViewSet)
router.register(r'expenses', ExpenseViewSet)
router.register(r'users', UserViewSet)
router.register(r'roles', GroupViewSet)
router.register(r'permissions', PermissionViewSet)

urlpatterns = [
    # Auth
    path('auth/login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/logout/', TokenBlacklistView.as_view(), name='token_blacklist'),
    path('auth/me/', CurrentUserView.as_view(), name='current_user'),

    # Dashboard
    path('dashboard/stats/', DashboardStatsView.as_view(), name='dashboard_stats'),
    path('dashboard/revenue-chart/', RevenueChartView.as_view(), name='revenue_chart'),
    path('dashboard/order-stats/', OrderStatsView.as_view(), name='order_stats'),

    # POS
    path('pos/checkout/', CheckoutView.as_view(), name='pos_checkout'),

    # Router URLs
    path('', include(router.urls)),
]
