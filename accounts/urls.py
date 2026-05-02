from django.urls import path

from . import views


urlpatterns = [
    # Public UI
    path('', views.public_home, name='public_home'),
    path('store/products/', views.public_products, name='public_products'),
    path('store/products/<int:product_id>/', views.public_product_detail, name='public_product_detail'),
    path('store/products/<int:product_id>/review/', views.submit_review, name='submit_review'),
    path('about/', views.public_about, name='public_about'),
    path('cart/', views.public_cart, name='public_cart'),
    path('checkout/', views.public_checkout_page, name='public_checkout_page'),
    path('public_checkout/', views.public_checkout, name='public_checkout'),
    path('api/search/', views.public_product_search, name='public_product_search'),
    path('api/upsells/', views.get_cart_upsells, name='get_cart_upsells'),
    path('api/cart-sync/', views.get_cart_items_data, name='get_cart_sync'),
    
    # Auth & Admin
    path('login/', views.login_view, name='login'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('logout/', views.logout_view, name='logout'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('manager-dashboard/', views.manager_dashboard, name='manager_dashboard'),
    path('user-dashboard/', views.user_dashboard, name='user_dashboard'),
    path('edit/<int:id>/', views.edit_product, name='edit_product'),
    path('delete/<int:id>/', views.delete_product, name='delete_product'),
    path('permissions/', views.permission_list, name='permission_list'),
    path('permissions/<int:user_id>/json/', views.user_permissions_json, name='user_permissions_json'),
    path('permissions/<int:user_id>/update/', views.update_user_permissions, name='update_user_permissions'),
    path('products/', views.product_list, name='product_list'),
    path('products/add/', views.add_product, name='add_product'),
    path('products/<int:id>/', views.product_detail, name='product_detail'),
    path('roles/create/', views.role_create, name='role_create'),
    path('roles/<int:id>/edit/', views.role_edit, name='role_edit'),
    path('users/', views.user_list, name='user_list'),
    path('users/add/', views.add_user, name='add_user'),
    path('users/<int:user_id>/roles/', views.user_roles, name='user_roles'),
    path('users/<int:user_id>/edit/', views.edit_user, name='edit_user'),
    path('inventory/', views.inventory_view, name='inventory'),
    path('stock/edit/<int:product_id>/', views.edit_stock, name='edit_stock'),
    path('stock/delete/<int:pk>/', views.delete_product, name='delete_product'),
    path('sales/', views.sales_page, name='sales'),
    path('sales/records/', views.sales_records, name='sales_records'),
    path('sell/', views.sell_product, name='sell_product'),
    path('roles/', views.role_list, name='role_list'),
    path('invoice/<int:invoice_id>/', views.generate_invoice, name='invoice'),
    
    # Expenses
    path('expenses/', views.expenses_page, name='expenses'),
    path('expenses/add/', views.add_expense, name='add_expense'),
    path('expenses/<int:expense_id>/delete/', views.delete_expense, name='delete_expense'),

    # Order Tracking
    path('track/', views.track_order_page, {'tracking_id': ''}, name='track_home'),
    path('track/<str:tracking_id>/', views.track_order_page, name='track_order'),
    path('track/<str:tracking_id>/refund/', views.public_refund_order, name='public_refund_order'),
    path('api/track/<str:tracking_id>/', views.track_order_api, name='track_order_api'),

    # Order Management (ERP)
    path('orders/', views.orders_dashboard, name='orders_dashboard'),
    path('orders/<int:order_id>/update/', views.update_order_status, name='update_order_status'),
    path('orders/<int:order_id>/cancel/', views.cancel_order, name='cancel_order'),

]
