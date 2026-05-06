from django.db import models
from django.contrib.auth.models import User


class APILog(models.Model):
    """
    Modèle de log optimisé pour SQL Server.
    """
    
    class LogLevel(models.TextChoices):
        DEBUG = 'DEBUG', 'Debug'
        INFO = 'INFO', 'Info'
        WARNING = 'WARN', 'Warning'
        ERROR = 'ERROR', 'Error'
        CRITICAL = 'CRIT', 'Critical'
    
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    level = models.CharField(max_length=5, choices=LogLevel.choices, db_index=True)
    user_id = models.IntegerField(null=True, blank=True, db_index=True)
    username = models.CharField(max_length=150, null=True, blank=True)
    endpoint = models.CharField(max_length=255)
    method = models.CharField(max_length=10)
    status_code = models.SmallIntegerField(db_index=True)
    execution_time_ms = models.IntegerField()
    client_ip_hash = models.CharField(max_length=16, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    request_body = models.TextField(null=True, blank=True)
    
    class Meta:
        db_table = 'api_logs'
        indexes = [
            models.Index(fields=['-timestamp', 'level'], name='idx_log_ts_level'),
            models.Index(fields=['endpoint', '-timestamp'], name='idx_log_endpoint'),
            models.Index(fields=['status_code', '-timestamp'], name='idx_log_status'),
        ]
    
    def __str__(self):
        return f"[{self.timestamp}] {self.level} - {self.endpoint}"


class ViewPermission(models.Model):
    """
    Table des vues/endpoints disponibles dans l'API.
    """
    code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    endpoint_pattern = models.CharField(max_length=255, help_text="Pattern regex de l'endpoint")
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'api_view_permissions'
    
    def __str__(self):
        return f"{self.code} - {self.name}"


class UserViewPermission(models.Model):
    """
    Association User <-> ViewPermission.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='view_permissions')
    view_permission = models.ForeignKey(ViewPermission, on_delete=models.CASCADE)
    granted_at = models.DateTimeField(auto_now_add=True)
    granted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='granted_permissions')
    
    class Meta:
        db_table = 'api_user_view_permissions'
        unique_together = ['user', 'view_permission']
    
    def __str__(self):
        return f"{self.user.username} -> {self.view_permission.code}"
        

class Transco_API(models.Model):
    
    NOM_API = models.CharField(max_length=100)
    CLIENT = models.CharField(max_length=50)
    NOM_TABLE = models.CharField(max_length=100)
    SCHEMA = models.CharField(max_length=10)
    DATE_LAST_MAJ = models.DateTimeField()
    
    class Meta:
        managed = False
        db_table = 'VIEW_X_API_CONFIG'
        
        