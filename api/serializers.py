from rest_framework import serializers
from django.contrib.auth.models import User, Group, Permission
from accounts.models import (
    Category, Brand, Product, Profile, Invoice, Sale, 
    Expense, Review, Order, OrderStatusLog, Activity
)

# --- Auth & User Serializers ---

class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ['id', 'name', 'codename', 'content_type']

class GroupSerializer(serializers.ModelSerializer):
    permissions = PermissionSerializer(many=True, read_only=True)
    permission_ids = serializers.PrimaryKeyRelatedField(
        many=True, write_only=True, queryset=Permission.objects.all(), source='permissions'
    )

    class Meta:
        model = Group
        fields = ['id', 'name', 'permissions', 'permission_ids']

class UserSerializer(serializers.ModelSerializer):
    groups = GroupSerializer(many=True, read_only=True)
    group_ids = serializers.PrimaryKeyRelatedField(
        many=True, write_only=True, queryset=Group.objects.all(), source='groups'
    )
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'is_active', 'groups', 'group_ids', 'password']

    def create(self, validated_data):
        password = validated_data.pop('password')
        groups_data = validated_data.pop('groups', [])
        user = User.objects.create_user(**validated_data)
        user.set_password(password)
        user.save()
        user.groups.set(groups_data)
        return user

# --- Product Serializers ---

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'

class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = '__all__'

class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.ReadOnlyField(source='category.name')
    brand_name = serializers.ReadOnlyField(source='brand.name')
    
    class Meta:
        model = Product
        fields = '__all__'

# --- POS & Sales Serializers ---

class SaleSerializer(serializers.ModelSerializer):
    product_name = serializers.ReadOnlyField(source='product.name')
    
    class Meta:
        model = Sale
        fields = '__all__'
        read_only_fields = ['total_amount', 'profit', 'created_by']

class InvoiceSerializer(serializers.ModelSerializer):
    items = SaleSerializer(many=True, read_only=True)
    creator_name = serializers.ReadOnlyField(source='created_by.username')
    order_status = serializers.ReadOnlyField(source='order.status')

    class Meta:
        model = Invoice
        fields = '__all__'
        read_only_fields = ['invoice_number', 'total_amount', 'total_profit', 'created_by']

# --- Order Serializers ---

class OrderStatusLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusLog
        fields = '__all__'

class OrderSerializer(serializers.ModelSerializer):
    logs = OrderStatusLogSerializer(many=True, read_only=True)
    timeline = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = '__all__'
        read_only_fields = ['tracking_id', 'placed_at', 'updated_at']

    def get_timeline(self, obj):
        return obj.get_timeline()

# --- Others ---

class ExpenseSerializer(serializers.ModelSerializer):
    creator_name = serializers.ReadOnlyField(source='created_by.username')

    class Meta:
        model = Expense
        fields = '__all__'
        read_only_fields = ['created_by']

class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = '__all__'

class ActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Activity
        fields = '__all__'

class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = '__all__'
