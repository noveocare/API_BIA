from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from rest_framework.authtoken.admin import TokenAdmin
from .models import APILog, ViewPermission, UserViewPermission, Transco_API

TokenAdmin.raw_id_fields = ['user']


# ========================================
# Admin pour APILog (existant)
# ========================================
@admin.register(APILog)
class APILogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'level', 'username', 'endpoint', 'method', 'status_code', 'execution_time_ms')
    list_filter = ('level', 'method', 'status_code', 'timestamp')
    search_fields = ('username', 'endpoint', 'error_message')
    readonly_fields = ('timestamp', 'level', 'user_id', 'username', 'endpoint', 'method', 
                       'status_code', 'execution_time_ms', 'client_ip_hash', 'error_message', 'request_body')
    ordering = ('-timestamp',)
    date_hierarchy = 'timestamp'
    
    def has_add_permission(self, request):
        return False  # Les logs ne doivent pas être créés manuellement
    
    def has_change_permission(self, request, obj=None):
        return False  # Les logs ne doivent pas être modifiés


# ========================================
# Admin pour ViewPermission
# ========================================
@admin.register(ViewPermission)
class ViewPermissionAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'endpoint_pattern', 'is_active', 'user_count')
    list_filter = ('is_active',)
    search_fields = ('code', 'name', 'description', 'endpoint_pattern')
    ordering = ('code',)
    
    fieldsets = (
        (None, {
            'fields': ('code', 'name', 'description')
        }),
        ('Configuration', {
            'fields': ('endpoint_pattern', 'is_active')
        }),
    )
    
    def user_count(self, obj):
        """Affiche le nombre d'utilisateurs ayant cette permission."""
        return obj.userviewpermission_set.count()
    user_count.short_description = "Utilisateurs"


# ========================================
# Admin pour UserViewPermission
# ========================================
@admin.register(UserViewPermission)
class UserViewPermissionAdmin(admin.ModelAdmin):
    list_display = ('user', 'view_permission', 'granted_at', 'granted_by')
    list_filter = ('view_permission', 'granted_at')
    search_fields = ('user__username', 'view_permission__code', 'view_permission__name')
    raw_id_fields = ('user', 'granted_by')
    autocomplete_fields = ['view_permission']
    ordering = ('-granted_at',)
    readonly_fields = ('granted_at',)
    
    fieldsets = (
        (None, {
            'fields': ('user', 'view_permission')
        }),
        ('Audit', {
            'fields': ('granted_at', 'granted_by'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        """Enregistre automatiquement l'utilisateur qui accorde la permission."""
        if not change:  # Seulement à la création
            obj.granted_by = request.user
        super().save_model(request, obj, form, change)


# ========================================
# Inline pour ajouter les permissions directement dans l'admin User
# ========================================
class UserViewPermissionInline(admin.TabularInline):
    model = UserViewPermission
    fk_name = 'user'  # Spécifie quelle ForeignKey utiliser
    extra = 1
    autocomplete_fields = ['view_permission']
    readonly_fields = ('granted_at', 'granted_by')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('view_permission')


# ========================================
# Extension de l'admin User pour inclure les permissions
# ========================================
class CustomUserAdmin(BaseUserAdmin):
    inlines = list(BaseUserAdmin.inlines) + [UserViewPermissionInline]
    list_display = list(BaseUserAdmin.list_display) + ['view_permissions_count']
    
    def view_permissions_count(self, obj):
        """Affiche le nombre de permissions API de l'utilisateur."""
        return obj.view_permissions.count()
    view_permissions_count.short_description = "Permissions API"


# Désinscrire l'admin User par défaut et réinscrire avec notre version
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
admin.site.register(Transco_API)


# ========================================
# Personnalisation de l'interface admin
# ========================================
admin.site.site_header = "NoveoCare API Administration"
admin.site.site_title = "NoveoCare API Admin"
admin.site.index_title = "Gestion de l'API Data HR"