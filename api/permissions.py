from rest_framework import permissions

class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow admins to edit it.
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user and request.user.is_staff

class HasModelPermission(permissions.DjangoModelPermissions):
    """
    Extends DjangoModelPermissions to also handle 'view' permissions.
    """
    perms_map = {
        'GET': ['%(app_label)s.view_%(model_name)s'],
        'OPTIONS': [],
        'HEAD': [],
        'POST': ['%(app_label)s.add_%(model_name)s'],
        'PUT': ['%(app_label)s.change_%(model_name)s'],
        'PATCH': ['%(app_label)s.change_%(model_name)s'],
        'DELETE': ['%(app_label)s.delete_%(model_name)s'],
    }

class HasRolePermission(permissions.BasePermission):
    """
    Permission check based on custom roles or specific permissions string.
    Usage: permission_classes = [HasRolePermission]
    Then define required_perms = ['accounts.can_edit_product'] in the view.
    """
    def has_permission(self, request, view):
        required_perms = getattr(view, 'required_perms', [])
        if not required_perms:
            return True
        return request.user.has_perms(required_perms)
