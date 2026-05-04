import json
from datetime import timedelta
import logging
from datetime import timedelta
from functools import wraps
from .models import Profile
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from .models import Sale, Invoice, Category, Brand, Review, Order, OrderStatusLog
from accounts.models import Activity, Product
from .forms import ProductForm
from django.contrib.auth.decorators import permission_required
from decimal import Decimal
from django.template.loader import render_to_string
from reportlab.pdfgen import canvas
from django.http import HttpResponse
logger = logging.getLogger(__name__)

ROLE_ADMIN = 'admin'
ROLE_MANAGER = 'manager'
ROLE_USER = 'user'
CUSTOM_PERMISSION_GROUPS = (
    {
        'key': 'product',
        'title': 'Product Permissions',
        'codenames': (
            'can_add_product',
            'can_edit_product',
            'can_delete_product',
            'can_view_product',
        ),
    },
    {
        'key': 'user',
        'title': 'User Permissions',
        'codenames': (
            'can_add_user',
            'can_edit_user',
            'can_delete_user',
        ),
    },

    # 🔥 ADD THIS (IMPORTANT)
    {
        'key': 'inventory',
        'title': 'Inventory Permissions',
        'codenames': (
            'view_stock',
            'edit_stock',
            'delete_stock',
        ),
    },
    {
        'key': 'sales',
        'title': 'Sales Permissions',
        'codenames': (
            'view_sales',
            'create_sale',
        ),
    },
)
CUSTOM_PERMISSION_CODENAMES = tuple(
    codename
    for group in CUSTOM_PERMISSION_GROUPS
    for codename in group['codenames']
)
PERMISSION_LABELS = {
    'can_add_product': 'Add Product',
    'can_edit_product': 'Edit Product',
    'can_delete_product': 'Delete Product',
    'can_view_product': 'View Products',

    'can_add_user': 'Add User',
    'can_edit_user': 'Edit User',
    'can_delete_user': 'Delete User',

    # 🔥 ADD THESE
    'view_stock': 'View Inventory',
    'edit_stock': 'Edit Stock',
    'delete_stock': 'Delete Stock',
    'view_sales': 'View Sales',
    'create_sale': 'Create Sale',
}
ROLE_CHOICES = (
    ('', 'No role'),
    ('Admin', 'Admin'),
    ('Manager', 'Manager'),
    ('User', 'User'),
)


def get_user_role_names(user):
    if not user.is_authenticated:
        return set()
    return {name.lower() for name in user.groups.values_list('name', flat=True)}


def has_role(user, role_name):
    return role_name.lower() in get_user_role_names(user)


def is_cashier(user):
    return user.is_authenticated and has_role(user, 'cashier')

def is_admin(user):
    return user.is_authenticated and (user.is_superuser or has_role(user, ROLE_ADMIN))


def is_manager(user):
    return user.is_authenticated and has_role(user, ROLE_MANAGER)


def is_normal_user(user):
    return user.is_authenticated


def get_dashboard_name(user):
    if is_admin(user):
        return 'admin_dashboard'

    if is_manager(user):
        return 'manager_dashboard'

    # ✅ DEFAULT FOR EVERYONE ELSE
    return 'user_dashboard'

def role_required(test_func):
    def decorator(view_func):
        @wraps(view_func)
        @login_required(login_url='login')
        def wrapped_view(request, *args, **kwargs):
            if test_func(request.user):
                return view_func(request, *args, **kwargs)

            logger.warning(
                'RBAC denied: user=%s groups=%s path=%s',
                request.user.username,
                sorted(get_user_role_names(request.user)),
                request.path,
            )
            raise PermissionDenied('You do not have permission to access this page.')

        return wrapped_view

    return decorator


def base_context(request, extra=None):
    context = {
        'can_manage_users': is_admin(request.user),
    }
    if extra:
        context.update(extra)
    return context


def login_view(request):
    # If already logged in → redirect
    if request.user.is_authenticated:
        return redirect(get_dashboard_name(request.user))

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        user = authenticate(request, username=username, password=password)

        # ❌ Invalid credentials
        if user is None:
            return render(
                request,
                'login.html',
                {'error': 'Invalid username or password.'},
                status=401,
            )

        # ✅ Login user
        login(request, user)

        logger.info(
            'Login successful: user=%s groups=%s',
            user.username,
            sorted(get_user_role_names(user)),
        )

        # ✅ ALWAYS redirect (no rejection anymore)
        dashboard_name = get_dashboard_name(user)

        # fallback safety (should never fail)
        if not dashboard_name:
            dashboard_name = 'user_dashboard'

        return redirect(dashboard_name)

    return render(request, 'login.html')


def logout_view(request):
    logout(request)
    return redirect('login')

@role_required(is_admin)
def admin_dashboard(request):
    # Use the full dashboard context so avatars, chart & activity all show
    return render(request, 'admin_dashboard.html', base_context(request, get_dashboard_context(request)))


@login_required(login_url='login')
def product_detail(request, id):
    if not request.user.has_perm('accounts.can_view_product'):
        raise PermissionDenied('You do not have permission to view products.')
    product = get_object_or_404(Product, id=id)
    return render(request, 'product_detail.html', base_context(request, {'product': product}))
   

def get_dashboard_context(request):
    User = get_user_model()
    today = timezone.localdate()

    chart_days = [today - timedelta(days=day) for day in range(6, -1, -1)]

    product_counts = {
        item['day']: item['total']
        for item in Product.objects.annotate(day=TruncDate('created_at'))
        .filter(day__in=chart_days)
        .values('day')
        .annotate(total=Count('id'))
    }

    # Fixed: total_sales = sum of all sale.total_amount
    total_sales_data = Sale.objects.aggregate(total=Sum('total_amount'))
    total_profit_data = Sale.objects.aggregate(total=Sum('profit'))
    
    total_sales = total_sales_data['total'] if total_sales_data['total'] else Decimal(0)
    total_profit = total_profit_data['total'] if total_profit_data['total'] else Decimal(0)

    return {
        'total_products': Product.objects.count(),
        'total_users': User.objects.count(),
        'total_sales': float(total_sales) if total_sales else 0,
        'total_profit': float(total_profit) if total_profit else 0,

        'activities': Activity.objects.order_by('-created_at')[:8],
        'chart_labels': json.dumps([day.strftime('%a') for day in chart_days]),
        'chart_data': json.dumps([product_counts.get(day, 0) for day in chart_days]),
        'users': User.objects.all(),
        'products': Product.objects.all(),
    }

@login_required(login_url='login')
def dashboard(request):
    return redirect(get_dashboard_name(request.user))

@role_required(is_manager)
def manager_dashboard(request):
    return render(request, 'manager_dashboard.html', base_context(request, get_dashboard_context(request)))


@role_required(is_normal_user)
def user_dashboard(request):
    return render(request, 'user_dashboard.html', base_context(request, get_dashboard_context(request)))


@login_required(login_url='login')
def product_list(request):
    if not request.user.has_perm('accounts.can_view_product'):
        raise PermissionDenied('You do not have permission to view products.')

    products = Product.objects.select_related('created_by').order_by('name')
    return render(request, 'products.html', base_context(request, {'products': products}))


@login_required(login_url='login')
def add_product(request):
    if not request.user.has_perm('accounts.can_add_product'):
        raise PermissionDenied('You do not have permission to add products.')

    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save(commit=False)
            product.created_by = request.user
            product.save()
            Activity.objects.create(message=f'Product created: {product.name}')
            messages.success(request, f'Product {product.name} was added successfully.')
            return redirect('product_list')
        else:
            return render(
                request,
                'add_product.html',
                base_context(request, {'error': 'Invalid data provided.', 'form': form}),
                status=400,
            )

    return render(request, 'add_product.html', base_context(request))


@login_required(login_url='login')
def edit_product(request, id):
    if not request.user.has_perm('accounts.can_edit_product'):
        raise PermissionDenied('You do not have permission to edit products.')

    product = get_object_or_404(Product, id=id)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            Activity.objects.create(message=f'Product updated: {product.name}')
            return redirect('product_list')
        else:
            return render(request, 'edit_product.html', base_context(request, {'product': product, 'form': form}))

    return render(request, 'edit_product.html', base_context(request, {'product': product}))


@require_POST
@login_required(login_url='login')
def delete_product(request, id):
    if not request.user.has_perm('accounts.can_delete_product'):
        raise PermissionDenied('You do not have permission to delete products.')

    product = get_object_or_404(Product, id=id)
    product_name = product.name
    product.delete()
    Activity.objects.create(message=f'Product deleted: {product_name}')
    return redirect('product_list')


def get_custom_permissions():
    permissions = Permission.objects.filter(
        codename__in=CUSTOM_PERMISSION_CODENAMES
    ).select_related('content_type')

    permission_map = {permission.codename: permission for permission in permissions}

    return [
        permission_map[codename]
        for codename in CUSTOM_PERMISSION_CODENAMES
        if codename in permission_map
    ]


def get_custom_permission_groups():
    permission_map = {permission.codename: permission for permission in get_custom_permissions()}
    return [
        {
            'key': group['key'],
            'title': group['title'],
            'permissions': [
                permission_map[codename]
                for codename in group['codenames']
                if codename in permission_map
            ],
        }
        for group in CUSTOM_PERMISSION_GROUPS
    ]


def get_permission_ids_from_request(request):
    return {
        int(permission_id)
        for permission_id in request.POST.getlist('permissions')
        if permission_id.isdigit()
    }


def get_role_form_context(errors=None, role=None, selected_permission_ids=None, role_name=''):
    return {
        'errors': errors or [],
        'labels': PERMISSION_LABELS,
        'permission_groups': get_custom_permission_groups(),
        'role': role,
        'role_name': role_name or (role.name if role else ''),
        'selected_permission_ids': selected_permission_ids or set(),
    }


@role_required(is_admin)
def role_list(request):
    roles = Group.objects.prefetch_related('permissions', 'user_set').order_by('name')
    return render(request, 'role_list.html', base_context(request, {'roles': roles}))


@role_required(is_admin)
def role_create(request):
    errors = []
    role_name = ''
    selected_permission_ids = set()
    permissions = get_custom_permissions()
    allowed_permission_ids = {permission.id for permission in permissions}

    if request.method == 'POST':
        role_name = request.POST.get('name', '').strip()
        selected_permission_ids = get_permission_ids_from_request(request)

        if not role_name:
            errors.append('Role name is required.')
        elif Group.objects.filter(name__iexact=role_name).exists():
            errors.append('Role name already exists.')

        if not selected_permission_ids.issubset(allowed_permission_ids):
            errors.append('Invalid permission selected.')

        if not errors:
            role = Group.objects.create(name=role_name)
            selected_permissions = [
                permission
                for permission in permissions
                if permission.id in selected_permission_ids
            ]
            role.permissions.set(selected_permissions)
            Activity.objects.create(message=f'Role created: {role.name}')
            messages.success(request, f'Role {role.name} was created successfully.')
            return redirect('role_list')

    context = get_role_form_context(
        errors=errors,
        role_name=role_name,
        selected_permission_ids=selected_permission_ids,
    )
    return render(request, 'role_create.html', base_context(request, context))


@role_required(is_admin)
def role_edit(request, id):
    role = get_object_or_404(Group, id=id)
    errors = []
    role_name = role.name
    permissions = get_custom_permissions()
    allowed_permission_ids = {permission.id for permission in permissions}
    selected_permission_ids = set(role.permissions.values_list('id', flat=True))

    if request.method == 'POST':
        role_name = request.POST.get('name', '').strip()
        selected_permission_ids = get_permission_ids_from_request(request)

        if not role_name:
            errors.append('Role name is required.')
        elif Group.objects.filter(name__iexact=role_name).exclude(id=role.id).exists():
            errors.append('Role name already exists.')

        if not selected_permission_ids.issubset(allowed_permission_ids):
            errors.append('Invalid permission selected.')

        if not errors:
            role.name = role_name
            role.save()
            selected_permissions = [
                permission
                for permission in permissions
                if permission.id in selected_permission_ids
            ]
            role.permissions.set(selected_permissions)
            Activity.objects.create(message=f'Role updated: {role.name}')
            messages.success(request, f'Role {role.name} was updated successfully.')
            return redirect('role_list')

    context = get_role_form_context(
        errors=errors,
        role=role,
        role_name=role_name,
        selected_permission_ids=selected_permission_ids,
    )
    return render(request, 'role_edit.html', base_context(request, context))


@role_required(is_admin)
def user_roles(request, user_id):
    User = get_user_model()
    user_obj = get_object_or_404(User, id=user_id)
    roles = Group.objects.order_by('name')
    selected_role_ids = set(user_obj.groups.values_list('id', flat=True))
    errors = []

    if request.method == 'POST':
        selected_role_ids = {
            int(role_id)
            for role_id in request.POST.getlist('roles')
            if role_id.isdigit()
        }
        allowed_role_ids = set(roles.values_list('id', flat=True))

        if not selected_role_ids.issubset(allowed_role_ids):
            errors.append('Invalid role selected.')

        if not errors:
            user_obj.groups.set(roles.filter(id__in=selected_role_ids))
            Activity.objects.create(message=f'Roles updated for user: {user_obj.username}')
            messages.success(request, f'Roles for {user_obj.username} were updated successfully.')
            return redirect('user_list')

    context = {
        'errors': errors,
        'roles': roles,
        'selected_role_ids': selected_role_ids,
        'user_obj': user_obj,
    }
    return render(request, 'user_roles.html', base_context(request, context))


@role_required(is_admin)
def permission_list(request):
    User = get_user_model()
    users = User.objects.order_by('username')
    return render(
        request,
        'permission.html',
        base_context(request, {'users': users, 'labels': PERMISSION_LABELS}),
    )


@role_required(is_admin)
def user_list(request):
    User = get_user_model()
    users = User.objects.prefetch_related('groups', 'user_permissions').order_by('username')
    return render(request, 'users.html', base_context(request, {'users': users}))


@role_required(is_admin)
def add_user(request):
    User = get_user_model()
    permissions = get_custom_permissions()
    errors = []
    selected_permission_ids = set()
    selected_role = ''
    username = ''

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')
        selected_role = request.POST.get('role', '')
        selected_permission_ids = {
            int(permission_id)
            for permission_id in request.POST.getlist('permissions')
            if permission_id.isdigit()
        }
        allowed_permission_ids = {permission.id for permission in permissions}

        if not username:
            errors.append('Username is required.')
        elif User.objects.filter(username__iexact=username).exists():
            errors.append('Username already exists.')

        if not password:
            errors.append('Password is required.')
        elif password != confirm_password:
            errors.append('Passwords do not match.')

        if selected_role and selected_role not in dict(ROLE_CHOICES):
            errors.append('Invalid role selected.')

        if not selected_permission_ids.issubset(allowed_permission_ids):
            errors.append('Invalid permission selected.')

        if not errors:
            user = User.objects.create_user(username=username, password=password)

            if selected_role:
                group, _ = Group.objects.get_or_create(name=selected_role)
                user.groups.add(group)

            selected_permissions = [
                permission
                for permission in permissions
                if permission.id in selected_permission_ids
            ]
            user.user_permissions.set(selected_permissions)

            Activity.objects.create(message=f'User created: {user.username}')
            messages.success(request, f'User {username} was created successfully.')
            return redirect('user_list')

    context = {
        'errors': errors,
        'labels': PERMISSION_LABELS,
        'permission_groups': get_custom_permission_groups(),
        'role_choices': ROLE_CHOICES,
        'selected_permission_ids': selected_permission_ids,
        'selected_role': selected_role,
        'username': username,
    }
    return render(request, 'add_user.html', base_context(request, context))


@role_required(is_admin)
def edit_user(request, user_id):
    User = get_user_model()
    user = get_object_or_404(User, id=user_id)

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        is_active = request.POST.get("is_active") == "on"
        is_staff = request.POST.get("is_staff") == "on"

        if username:
            user.username = username

        user.is_active = is_active
        user.is_staff = is_staff

        # IMAGE UPDATE
        image = request.FILES.get("image")

        # ✅ Ensure profile exists
        profile, created = Profile.objects.get_or_create(user=user)

        if image:
           profile.image = image
           profile.save()

        user.save()

        Activity.objects.create(message=f'User updated: {user.username}')
        return redirect("user_list")

    return render(request, "edit_user.html", base_context(request, {"user_obj": user}))
@role_required(is_admin)
def user_permissions_json(request, user_id):
    User = get_user_model()
    user_obj = get_object_or_404(User, id=user_id)

    groups = [
        {
            'key': group['key'],
            'title': group['title'],
            'permissions': [
                {
                    'id': permission.id,
                    'codename': permission.codename,
                    'label': PERMISSION_LABELS.get(permission.codename, permission.name),
                    'name': permission.name,
                    'assigned': user_obj.is_superuser or user_obj.has_perm(
                        f'accounts.{permission.codename}'
                    ),
                }
                for permission in group['permissions']
            ],
        }
        for group in get_custom_permission_groups()
    ]

    return JsonResponse({
        'user': {
            'id': user_obj.id,
            'username': user_obj.username,
            'is_superuser': user_obj.is_superuser,
        },
        'groups': groups,
    })


@require_POST
@role_required(is_admin)
def update_user_permissions(request, user_id):
    User = get_user_model()
    user_obj = get_object_or_404(User, id=user_id)

    allowed_permissions = get_custom_permissions()
    allowed_ids = {permission.id for permission in allowed_permissions}

    if request.content_type == 'application/json':
        try:
            payload = json.loads(request.body or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON payload.'}, status=400)
        submitted_permissions = payload.get('permissions', [])
    else:
        submitted_permissions = request.POST.getlist('permissions')

    selected_ids = set()
    for permission_id in submitted_permissions:
        try:
            selected_ids.add(int(permission_id))
        except (TypeError, ValueError):
            return JsonResponse({'error': 'Invalid permission selected.'}, status=400)

    if not selected_ids.issubset(allowed_ids):
        return JsonResponse({'error': 'Invalid permission selected.'}, status=400)

    selected_permissions = [
        permission
        for permission in allowed_permissions
        if permission.id in selected_ids
    ]
    user_obj.user_permissions.remove(*allowed_permissions)
    user_obj.user_permissions.add(*selected_permissions)

    return JsonResponse({'success': True})
@login_required
@permission_required('accounts.view_stock', raise_exception=True)
def inventory_view(request):
    products = Product.objects.all().distinct()   # 🔥 ADD DISTINCT
    return render(request, 'inventory.html', {'products': products})

@login_required
@permission_required('accounts.view_sales', raise_exception=True)
def sales_page(request):
    products = Product.objects.all()
    return render(request, 'sales.html', {'products': products})

@require_POST
@login_required
@permission_required('accounts.create_sale', raise_exception=True)
def sell_product(request):
    try:
        data = json.loads(request.body)
        items = data.get('items', [])
        
        if not items:
            return JsonResponse({'error': 'Cart is empty'}, status=400)
            
        from django.db import transaction
        with transaction.atomic():
            # Create Invoice first
            invoice = Invoice.objects.create(
                created_by=request.user,
                payment_method=data.get('payment_method', 'Cash').title()
            )
            
            total_amount = Decimal(0)
            total_discount = Decimal(0)
            total_profit = Decimal(0)
            
            for item in items:
                product_id = item.get('product_id')
                quantity = int(item.get('quantity', 0))
                discount = Decimal(str(item.get('discount', 0)))
                
                if not product_id or quantity <= 0:
                    raise ValueError('Invalid product or quantity in cart')
                    
                product = get_object_or_404(Product, id=product_id)
                
                selling_price_data = item.get('selling_price')
                if selling_price_data is not None:
                    selling_price = Decimal(str(selling_price_data))
                else:
                    selling_price = product.price
                    
                if selling_price <= 0:
                    raise ValueError('Selling price must be greater than 0')
                if discount < 0:
                    raise ValueError('Discount cannot be negative')
                    
                # Create Sale item
                sale = Sale.objects.create(
                    invoice=invoice,
                    product=product,
                    quantity=quantity,
                    selling_price=selling_price,
                    buying_price=product.buying_price,
                    discount=discount,
                    created_by=request.user,
                )
                
                total_amount += sale.total_amount
                total_discount += sale.discount
                total_profit += sale.profit
                
            # Update Invoice totals
            invoice.total_amount = total_amount
            invoice.total_discount = total_discount
            invoice.total_profit = total_profit
            invoice.save()
            
        return JsonResponse({
            'success': True,
            'invoice_url': f'/invoice/{invoice.id}/'
        })
        
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
            
           
       
@login_required
@permission_required('accounts.edit_stock', raise_exception=True)
def edit_stock(request, product_id):
    if request.method == "POST":
        import json
        data = json.loads(request.body)

        qty = int(data.get("quantity", 0))
        action = data.get("action")

        if qty <= 0:
            return JsonResponse({"error": "Invalid quantity"}, status=400)

        product = get_object_or_404(Product, id=product_id)

        if action == "add":
            product.stock += qty

        elif action == "minus":
            if product.stock < qty:
                return JsonResponse({"error": "Not enough stock"}, status=400)
            product.stock -= qty

        product.save()

        return JsonResponse({"success": True})

    return JsonResponse({"error": "Invalid request"}, status=400)


@login_required
@permission_required('accounts.view_sales', raise_exception=True)
def sales_records(request):
    User = get_user_model()
    invoices = Invoice.objects.select_related('created_by').prefetch_related('items__product').order_by('-created_at')

    # Apply filters
    date_filter = request.GET.get('date', '')
    user_filter = request.GET.get('user', '')
    product_filter = request.GET.get('product', '')

    if date_filter == 'today':
        invoices = invoices.filter(created_at__date=timezone.localdate())
    elif date_filter == 'week':
        today = timezone.localdate()
        start_of_week = today - timedelta(days=today.weekday())
        invoices = invoices.filter(created_at__date__gte=start_of_week)

    if user_filter:
        invoices = invoices.filter(created_by_id=user_filter)

    if product_filter:
        invoices = invoices.filter(items__product_id=product_filter).distinct()

    # Context data for filters
    users = User.objects.filter(invoice__isnull=False).distinct().order_by('username')
    products = Product.objects.filter(sale__isnull=False).distinct().order_by('name')

    context = {
        'invoices': invoices,
        'users': users,
        'products': products,
        'selected_date': date_filter,
        'selected_user': user_filter,
        'selected_product': product_filter,
    }
    return render(request, 'sales_records.html', base_context(request, context))


def generate_invoice(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id)
    items = invoice.items.all()

    # Dynamic height calculation
    base_height = 320
    item_height = 15
    height = base_height + (len(items) * item_height)
    width = 226

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{invoice.invoice_number}.pdf"'

    p = canvas.Canvas(response, pagesize=(width, height))

    y = height - 30

    # =========================
    # HEADER
    # =========================
    p.setFont("Courier-Bold", 14)
    p.drawCentredString(width/2, y, "MY STORE")
    y -= 15

    p.setFont("Courier", 10)
    p.drawCentredString(width/2, y, "1234 Main Street")
    y -= 12
    p.drawCentredString(width/2, y, "Rawalpindi, Pakistan")
    y -= 12
    p.drawCentredString(width/2, y, "0300-1234567")
    y -= 20

    # Dotted line
    p.setFont("Courier", 10)
    p.drawString(10, y, "." * 34)
    y -= 15

    # =========================
    # ITEM ROWS
    # =========================
    p.setFont("Courier", 10)
    for sale in items:
        # Left side: Item Name (truncated to fit)
        # Right side: Total Price
        name = sale.product.name[:15]
        if sale.quantity > 1:
            name = f"{sale.quantity}x {name}"
            
        p.drawString(10, y, name[:20])
        p.drawRightString(216, y, f"Rs {sale.total_price:.2f}")
        y -= 15

    # =========================
    # TOTAL SECTION
    # =========================
    p.drawString(10, y, "." * 34)
    y -= 15

    p.setFont("Courier", 10)
    p.drawString(10, y, "Sub Total")
    p.drawRightString(216, y, f"Rs {(invoice.total_amount + invoice.total_discount):.2f}")
    y -= 15

    if invoice.total_discount > 0:
        p.drawString(10, y, "Discount")
        p.drawRightString(216, y, f"-Rs {invoice.total_discount:.2f}")
        y -= 15

    p.drawString(10, y, "." * 34)
    y -= 20

    p.setFont("Courier-Bold", 12)
    p.drawString(10, y, "TOTAL")
    p.drawRightString(216, y, f"Rs {invoice.total_amount:.2f}")
    y -= 15

    p.setFont("Courier", 10)
    p.drawString(10, y, "." * 34)
    y -= 20

    # =========================
    # INFO SECTION
    # =========================
    p.setFont("Courier", 9)
    p.drawString(10, y, "Paid By:")
    
    # Display friendly payment method
    method = invoice.payment_method.lower()
    if method == 'bank':
        display_method = "Bank Transfer"
    elif method == 'card':
        display_method = "Card / Online"
    else:
        display_method = method.title()
        
    p.drawRightString(216, y, display_method)
    y -= 20
    
    p.drawString(10, y, f"{invoice.created_at.strftime('%m/%d/%Y %H:%M')}")
    y -= 12
    p.drawString(10, y, f"Trans ID: {invoice.invoice_number}")
    y -= 12
    p.drawString(10, y, f"Cashier:  {invoice.created_by.username if invoice.created_by else 'System'}")
    y -= 25

    # =========================
    # FOOTER
    # =========================
    p.setFont("Courier", 9)
    p.drawCentredString(width/2, y, "Thank You For Supporting")
    y -= 12
    p.drawCentredString(width/2, y, "Local Business!")

    p.showPage()
    p.save()

    return response

# ==========================================
# PUBLIC E-COMMERCE VIEWS
# ==========================================

def public_home(request):
    featured_products = Product.objects.filter(is_active=True).order_by('-created_at')[:8]
    features = [
        ('shield-check', 'Genuine Products', 'Every item is sourced from verified suppliers for your peace of mind.'),
        ('truck', 'Fast Delivery', 'Same-day processing on all orders placed before 6PM.'),
        ('headphones', '24/7 Support', 'Our support team is always here to help you out.'),
        ('rotate-ccw', 'Easy Returns', 'Not happy? Return within 7 days, no questions asked.'),
    ]
    return render(request, 'public_home.html', {'products': featured_products, 'features': features})

def public_products(request):
    from django.db.models import Avg, Count, Q
    
    # Base queryset with annotations
    products = Product.objects.filter(is_active=True).annotate(
        avg_rating=Avg('reviews__rating')
    )
    
    # 1. Filtering
    q = request.GET.get('q', '').strip()
    if q:
        products = products.filter(Q(name__icontains=q) | Q(description__icontains=q))
        
    category_ids = request.GET.getlist('category')
    if category_ids and '' not in category_ids:
        products = products.filter(category_id__in=category_ids)
        
    brand_ids = request.GET.getlist('brand')
    if brand_ids and '' not in brand_ids:
        products = products.filter(brand_id__in=brand_ids)
        
    min_price = request.GET.get('min_price')
    if min_price:
        products = products.filter(price__gte=min_price)
        
    max_price = request.GET.get('max_price')
    if max_price:
        products = products.filter(price__lte=max_price)
        
    min_rating = request.GET.get('rating')
    if min_rating:
        products = products.filter(avg_rating__gte=min_rating)
        
    stock_status = request.GET.get('stock')
    if stock_status == 'in_stock':
        products = products.filter(stock__gt=0)
    elif stock_status == 'out_of_stock':
        products = products.filter(stock__lte=0)
        
    # 2. Sorting
    sort = request.GET.get('sort', 'newest')
    if sort == 'low_high':
        products = products.order_by('price')
    elif sort == 'high_low':
        products = products.order_by('-price')
    elif sort == 'popular':
        products = products.order_by('-avg_rating', '-created_at')
    else: # newest
        products = products.order_by('-created_at')
        
    # 3. Sidebar Metadata (Counts)
    # Get all categories and brands with product counts (ignoring current filter but respecting search q)
    base_qs = Product.objects.filter(is_active=True)
    if q:
        base_qs = base_qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
        
    categories = Category.objects.annotate(
        count=Count('products', filter=Q(products__is_active=True, products__id__in=base_qs.values('id')))
    ).order_by('name')
    
    brands = Brand.objects.annotate(
        count=Count('products', filter=Q(products__is_active=True, products__id__in=base_qs.values('id')))
    ).order_by('name')

    # Get dynamic specs from results
    # For simplicity, we'll extract common keys from the resulting products
    # In a real app, this might be more structured
    
    # 4. Dynamic Filters (Specifications)
    # If a category is selected, we could show specs common to that category
    # For now, we'll extract all unique keys and values from the current product set
    dynamic_filters = {}
    for p in products:
        if p.specifications:
            for key, value in p.specifications.items():
                if key not in dynamic_filters:
                    dynamic_filters[key] = set()
                dynamic_filters[key].add(value)
    
    # Convert sets to sorted lists
    for key in dynamic_filters:
        dynamic_filters[key] = sorted(list(dynamic_filters[key]))

    # Handle spec filtering from request
    # Spec filters come as spec_KEY=VALUE
    spec_params = {k[5:]: v for k, v in request.GET.items() if k.startswith('spec_')}
    for key, value in spec_params.items():
        if value:
            products = products.filter(specifications__contains={key: value})

    context = {
        'products': products,
        'categories': categories,
        'brands': brands,
        'current_categories': category_ids,
        'current_brands': brand_ids,
        'min_price': min_price,
        'max_price': max_price,
        'current_rating': min_rating,
        'current_stock': stock_status,
        'current_sort': sort,
        'search_query': q,
        'dynamic_filters': dynamic_filters,
        'current_specs': spec_params,
    }
    
    # AJAX Support: If it's an AJAX request, return only the product grid
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('ajax') == '1':
        return render(request, 'partials/product_grid.html', context)
        
    return render(request, 'public_products.html', context)

def public_product_search(request):
    q = request.GET.get('q', '').strip()
    if not q:
        return JsonResponse({'products': []})
        
    products = Product.objects.filter(is_active=True, name__icontains=q).order_by('-created_at')[:10]
    
    results = []
    for p in products:
        results.append({
            'id': p.id,
            'name': p.name,
            'price': str(p.price),
            'image': p.image.url if p.image else '',
        })
        
    return JsonResponse({'products': results})

@require_POST
def get_cart_upsells(request):
    try:
        data = json.loads(request.body)
        item_ids = data.get('item_ids', [])
        
        if not item_ids:
             return JsonResponse({'upsells': []})
             
        base_products = Product.objects.filter(id__in=item_ids)
        upsell_ids = set()
        for p in base_products:
             upsell_ids.update(p.upsell_products.filter(is_active=True).values_list('id', flat=True))
             
        for i in item_ids:
             if int(i) in upsell_ids:
                 upsell_ids.remove(int(i))
                 
        upsells = Product.objects.filter(id__in=upsell_ids).distinct()[:4]
        
        results = []
        for p in upsells:
            results.append({
                'id': p.id,
                'name': p.name,
                'price': str(p.price),
                'image': p.image.url if p.image else '',
                'stock': p.stock,
                'compare_at_price': str(p.compare_at_price) if p.compare_at_price else None,
            })
            
        return JsonResponse({'upsells': results})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@require_POST
def get_cart_items_data(request):
    """Returns image and price data for a list of product IDs to repair/sync the public cart."""
    try:
        data = json.loads(request.body)
        item_ids = data.get('item_ids', [])
        if not item_ids:
            return JsonResponse({'items': {}})
            
        products = Product.objects.filter(id__in=item_ids, is_active=True)
        results = {}
        for p in products:
            results[str(p.id)] = {
                'image': p.image.url if p.image else '',
                'price': str(p.price),
                'stock': p.stock,
                'name': p.name,
                'compare_at_price': str(p.compare_at_price) if p.compare_at_price else None
            }
        return JsonResponse({'items': results})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

def public_about(request):
    return render(request, 'public_about.html')

def public_cart(request):
    return render(request, 'public_cart.html')

def public_checkout_page(request):
    return render(request, 'public_checkout_page.html')

@require_POST
def public_checkout(request):
    try:
        data = json.loads(request.body)
        items = data.get('items', [])
        
        if not items:
            return JsonResponse({'error': 'Cart is empty'}, status=400)
            
        # Validate Card Expiry if payment method is Card
        payment_method = data.get('payment_method', 'Cash').title()
        if payment_method == 'Card':
            card_expiry = data.get('card_expiry', '').strip()
            if not card_expiry or '/' not in card_expiry:
                return JsonResponse({'error': 'Card expiry date (MM/YY) is required.'}, status=400)
            try:
                parts = card_expiry.split('/')
                month = int(parts[0])
                year = int('20' + parts[1])
                
                from django.utils import timezone
                now = timezone.now()
                if month < 1 or month > 12:
                    return JsonResponse({'error': 'Invalid month in card expiry.'}, status=400)
                if year < now.year or (year == now.year and month < now.month):
                    return JsonResponse({'error': 'This card has already expired. Please use a valid card.'}, status=400)
            except (ValueError, IndexError):
                return JsonResponse({'error': 'Invalid card expiry format. Use MM/YY.'}, status=400)

        from django.db import transaction
        with transaction.atomic():
            invoice = Invoice.objects.create(created_by=None, payment_method=payment_method)
            
            total_amount = Decimal(0)
            total_discount = Decimal(0)
            total_profit = Decimal(0)
            
            for item in items:
                product_id = item.get('product_id')
                quantity = int(item.get('quantity', 0))
                
                if not product_id or quantity <= 0:
                    raise ValueError('Invalid product or quantity in cart')
                    
                product = get_object_or_404(Product, id=product_id)
                selling_price = product.price
                discount = Decimal(0)
                
                sale = Sale.objects.create(
                    invoice=invoice,
                    product=product,
                    quantity=quantity,
                    selling_price=selling_price,
                    buying_price=product.buying_price,
                    discount=discount,
                    created_by=None,
                )
                
                total_amount += sale.total_amount
                total_discount += sale.discount
                total_profit += sale.profit
                
            invoice.total_amount = total_amount
            invoice.total_discount = total_discount
            invoice.total_profit = total_profit
            invoice.save()

            # Auto-create an Order for public checkout
            customer_name  = data.get('customer_name', '').strip()
            customer_email = data.get('customer_email', '').strip()
            customer_phone = data.get('customer_phone', '').strip()
            shipping_addr  = data.get('shipping_address', '').strip()
            from datetime import date, timedelta
            est_delivery = date.today() + timedelta(days=5)
            order = Order.objects.create(
                invoice=invoice,
                customer_name=customer_name,
                customer_email=customer_email,
                customer_phone=customer_phone,
                shipping_address=shipping_addr,
                estimated_delivery=est_delivery,
            )
            # Log the initial placed event
            OrderStatusLog.objects.create(order=order, status=Order.STATUS_PLACED)

        return JsonResponse({
            'success': True,
            'invoice_url': f'/invoice/{invoice.id}/',
            'invoice_number': invoice.invoice_number,
            'tracking_id': order.tracking_id,
            'track_url': f'/track/{order.tracking_id}/',
        })
        
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def public_product_detail(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_active=True)
    reviews = product.reviews.select_related('user').all()
    user_has_reviewed = False
    if request.user.is_authenticated:
        user_has_reviewed = product.reviews.filter(user=request.user).exists()
    
    context = {
        'product': product,
        'reviews': reviews,
        'user_has_reviewed': user_has_reviewed,
    }
    return render(request, 'public_product_detail.html', context)

@require_POST
def submit_review(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    rating = request.POST.get('rating')
    comment = request.POST.get('comment', '').strip()
    name = request.POST.get('name', '').strip()
    email = request.POST.get('email', '').strip()

    if not rating or not name or not email:
        messages.error(request, 'Please provide name, email, and a rating.')
        return redirect('public_product_detail', product_id=product_id)

    try:
        Review.objects.update_or_create(
            product=product,
            email=email,
            defaults={
                'name': name,
                'rating': int(rating),
                'comment': comment,
                'user': request.user if request.user.is_authenticated else None
            }
        )
        messages.success(request, 'Thank you for your review!')
    except Exception as e:
        messages.error(request, f'Error submitting review: {str(e)}')

    return redirect('public_product_detail', product_id=product_id)


# ==========================================
# EXPENSE SYSTEM VIEWS
# ==========================================

from .models import Expense
from datetime import date as date_type

@login_required
def expenses_page(request):
    from django.db.models import Sum
    from datetime import timedelta

    # Date filter
    date_filter = request.GET.get('date', 'today')
    today = timezone.localdate()

    if date_filter == 'today':
        expenses = Expense.objects.filter(date=today)
    elif date_filter == 'week':
        start = today - timedelta(days=today.weekday())
        expenses = Expense.objects.filter(date__gte=start)
    elif date_filter == 'month':
        expenses = Expense.objects.filter(date__year=today.year, date__month=today.month)
    else:
        expenses = Expense.objects.all()

    # Totals
    total_expenses = expenses.aggregate(total=Sum('amount'))['total'] or 0

    # Sales profit for same period
    if date_filter == 'today':
        invoices_qs = Invoice.objects.filter(created_at__date=today)
    elif date_filter == 'week':
        start = today - timedelta(days=today.weekday())
        invoices_qs = Invoice.objects.filter(created_at__date__gte=start)
    elif date_filter == 'month':
        invoices_qs = Invoice.objects.filter(created_at__year=today.year, created_at__month=today.month)
    else:
        invoices_qs = Invoice.objects.all()

    gross_profit = invoices_qs.aggregate(total=Sum('total_profit'))['total'] or 0
    total_revenue = invoices_qs.aggregate(total=Sum('total_amount'))['total'] or 0
    net_profit = gross_profit - total_expenses

    context = {
        'expenses': expenses,
        'total_expenses': total_expenses,
        'gross_profit': gross_profit,
        'total_revenue': total_revenue,
        'net_profit': net_profit,
        'date_filter': date_filter,
        'expense_categories': Expense.CATEGORY_CHOICES,
        'filter_options': [
            ('today', 'Today'),
            ('week', 'This Week'),
            ('month', 'This Month'),
            ('all', 'All Time'),
        ],
    }
    return render(request, 'expenses.html', base_context(request, context))


@login_required
@require_POST
def add_expense(request):
    try:
        title = request.POST.get('title', '').strip()
        amount = request.POST.get('amount', '0')
        category = request.POST.get('category', 'other')
        description = request.POST.get('description', '').strip()
        exp_date = request.POST.get('date', timezone.localdate())

        if not title:
            messages.error(request, 'Title is required.')
            return redirect('expenses')
        
        amount = Decimal(str(amount))
        if amount <= 0:
            messages.error(request, 'Amount must be greater than 0.')
            return redirect('expenses')

        Expense.objects.create(
            title=title,
            amount=amount,
            category=category,
            description=description,
            date=exp_date,
            created_by=request.user,
        )
        messages.success(request, f'Expense "{title}" added successfully!')
    except Exception as e:
        messages.error(request, f'Error: {str(e)}')

    return redirect('expenses')


@login_required
@require_POST
def delete_expense(request, expense_id):
    expense = get_object_or_404(Expense, id=expense_id)
    expense.delete()
    messages.success(request, 'Expense deleted.')
    return redirect('expenses')


# ==========================================
# ORDER TRACKING VIEWS
# ==========================================

def track_order_page(request, tracking_id):
    """Public-facing order tracking page."""
    order = None
    error = None
    try:
        order = Order.objects.get(tracking_id=tracking_id.upper())
    except Order.DoesNotExist:
        error = f'No order found with tracking ID: {tracking_id}'
    return render(request, 'public_track_order.html', {'order': order, 'error': error, 'tracking_id': tracking_id})


@require_POST
def public_refund_order(request, tracking_id):
    """Public view to allow customers to refund delivered orders."""
    order = get_object_or_404(Order, tracking_id=tracking_id.upper())
    
    if order.status != Order.STATUS_DELIVERED:
        messages.error(request, 'Only delivered orders can be refunded online. For other cases, please contact support.')
        return redirect('track_order', tracking_id=tracking_id)
        
    try:
        order.cancel_and_restock(note="Refunded by customer via tracking portal")
        messages.success(request, 'Your refund request has been processed successfully. The items have been returned to our inventory.')
    except Exception as e:
        messages.error(request, f'Error processing refund: {str(e)}')
        
    return redirect('track_order', tracking_id=tracking_id)


def track_order_api(request, tracking_id):
    """JSON API for order status — used by the auto-refresh frontend."""
    try:
        order = Order.objects.get(tracking_id=tracking_id.upper())
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Order not found', 'tracking_id': tracking_id}, status=404)

    def fmt(dt):
        return dt.strftime('%d %b %Y, %I:%M %p') if dt else None

    pipeline_steps = [
        {
            'status': s,
            'label': dict(Order.STATUS_CHOICES)[s],
            'state': step['state'],
            'timestamp': fmt(step['timestamp']),
        }
        for s, step in zip(
            Order.STATUS_PIPELINE,
            [
                {'state': st['state'], 'timestamp': st['timestamp']}
                for st in order.get_timeline()
            ]
        )
    ]

    return JsonResponse({
        'tracking_id':       order.tracking_id,
        'status':            order.status,
        'status_display':    order.get_status_display(),
        'customer_name':     order.customer_name,
        'placed_at':         fmt(order.placed_at),
        'updated_at':        fmt(order.updated_at),
        'estimated_delivery':str(order.estimated_delivery) if order.estimated_delivery else None,
        'courier_name':      order.courier_name,
        'courier_tracking':  order.courier_tracking,
        'cancelled':         order.status == Order.STATUS_CANCELLED,
        'cancelled_at':      fmt(order.cancelled_at),
        'pipeline':          pipeline_steps,
        'invoice_number':    order.invoice.invoice_number if order.invoice else None,
    })


@login_required
def orders_dashboard(request):
    """ERP dashboard — order list and management."""
    from django.db.models import Count, Q

    status_filter = request.GET.get('status', '')
    q = request.GET.get('q', '').strip()
    date_filter = request.GET.get('date', '')

    # Always query the FULL set for accurate counts
    all_orders = Order.objects.select_related('invoice').order_by('-placed_at')

    # Per-status counts (always from full queryset, ignores filter)
    status_counts_qs = all_orders.values('status').annotate(count=Count('id'))
    status_counts = {item['status']: item['count'] for item in status_counts_qs}

    # Build stats list for template
    status_stats = [
        {
            'code': code,
            'label': label,
            'count': status_counts.get(code, 0),
        }
        for code, label in Order.STATUS_CHOICES
    ]
    total_orders = all_orders.count()

    # Apply filters for the table
    orders = all_orders
    if status_filter:
        orders = orders.filter(status=status_filter)
    
    if q:
        orders = orders.filter(
            Q(tracking_id__icontains=q) |
            Q(customer_name__icontains=q) |
            Q(customer_email__icontains=q) |
            Q(customer_phone__icontains=q)
        )

    if date_filter == 'today':
        orders = orders.filter(placed_at__date=timezone.localdate())
    elif date_filter == 'week':
        today = timezone.localdate()
        start = today - timedelta(days=today.weekday())
        orders = orders.filter(placed_at__date__gte=start)
    elif date_filter == 'month':
        today = timezone.localdate()
        orders = orders.filter(placed_at__year=today.year, placed_at__month=today.month)

    context = {
        'orders': orders,
        'status_filter': status_filter,
        'date_filter': date_filter,
        'search_query': q,
        'status_choices': Order.STATUS_CHOICES,
        'status_stats': status_stats,
        'total_orders': total_orders,
    }
    return render(request, 'orders_dashboard.html', base_context(request, context))


@login_required
@require_POST
def update_order_status(request, order_id):
    """ERP: manually set order status from dashboard form."""
    order = get_object_or_404(Order, id=order_id)
    new_status = request.POST.get('status', '').strip()
    note       = request.POST.get('note', '').strip()

    valid = dict(Order.STATUS_CHOICES)
    if new_status not in valid:
        messages.error(request, 'Invalid status.')
        return redirect('orders_dashboard')

    try:
        if new_status == Order.STATUS_CANCELLED:
            order.cancel_and_restock(note=note)
            messages.success(request, f'Order {order.tracking_id} cancelled and items restocked.')
        else:
            order.set_status(new_status)
            if note:
                # Attach note to the latest log entry
                latest_log = order.logs.last()
                if latest_log:
                    latest_log.note = note
                    latest_log.save(update_fields=['note'])
            messages.success(request, f'Order {order.tracking_id} updated to "{valid[new_status]}".')
    except ValueError as e:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
        messages.error(request, str(e))

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'status_display': valid[new_status]})

    return redirect('orders_dashboard')


@login_required
@require_POST
def cancel_order(request, order_id):
    """ERP: dedicated cancellation view with restocking."""
    order = get_object_or_404(Order, id=order_id)
    note = request.POST.get('note', 'Cancelled by administrator').strip()
    
    try:
        order.cancel_and_restock(note=note)
        messages.success(request, f'Order {order.tracking_id} has been cancelled and refunded (restocked).')
    except Exception as e:
        messages.error(request, f'Error cancelling order: {str(e)}')
        
    return redirect('orders_dashboard')