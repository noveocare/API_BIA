import time
import json
from django.utils.deprecation import MiddlewareMixin


class APILoggingMiddleware(MiddlewareMixin):
    """
    Middleware de logging automatique.
    Log uniquement les requêtes POST de façon asynchrone.
    """
    
    EXCLUDED_PATHS = (
        '/api/token/',
        '/api/token/refresh/',
    )
    
    # Champs sensibles à masquer
    SENSITIVE_FIELDS = ('password', 'token', 'secret', 'pwd', 'api_key')
    
    def process_request(self, request):
        if request.method == 'POST':
            request._log_start_time = time.perf_counter()
            # Capturer le body ici car il ne sera plus lisible après
            try:
                request._log_body = request.body.decode('utf-8')
            except:
                request._log_body = None
    
    def process_response(self, request, response):
        if request.method != 'POST':
            return response
        
        if request.path in self.EXCLUDED_PATHS:
            return response
        
        # Calcul du temps d'exécution
        start = getattr(request, '_log_start_time', None)
        exec_time_ms = int((time.perf_counter() - start) * 1000) if start else 0
        
        # User info
        user_id = None
        username = None
        
        if hasattr(request, 'user') and request.user.is_authenticated:
            user_id = request.user.id
            username = request.user.username
        else:
            user_id, username = self._get_user_from_jwt(request)
        
        # IP client
        client_ip = self._get_client_ip(request)
        
        # Niveau de log
        level = 'INFO'
        if response.status_code >= 500:
            level = 'ERROR'
        elif response.status_code >= 400:
            level = 'WARN'
        
        # Message d'erreur
        error_msg = None
        if response.status_code >= 400:
            try:
                error_msg = response.content.decode('utf-8')[:500]
            except:
                pass
        
        # Request body (masquer les champs sensibles)
        request_body = self._get_safe_body(request)
        
        from API.services.log_service import log_api_call
        
        log_api_call(
            endpoint=request.path,
            method=request.method,
            status_code=response.status_code,
            execution_time_ms=exec_time_ms,
            user_id=user_id,
            username=username,
            client_ip=client_ip,
            error_message=error_msg,
            request_body=request_body,
            level=level,
        )
        
        return response
    
    def _get_safe_body(self, request) -> str:
        """Récupère le body en masquant les champs sensibles."""
        raw_body = getattr(request, '_log_body', None)
        if not raw_body:
            return None
        
        try:
            data = json.loads(raw_body)
            self._mask_sensitive(data)
            return json.dumps(data, ensure_ascii=False)[:2000]  # Limite 2000 chars
        except:
            # Si pas du JSON valide, retourner tel quel (tronqué)
            return raw_body[:2000]
    
    def _mask_sensitive(self, data):
        """Masque récursivement les champs sensibles."""
        if isinstance(data, dict):
            for key in data:
                if any(s in key.lower() for s in self.SENSITIVE_FIELDS):
                    data[key] = '***MASKED***'
                else:
                    self._mask_sensitive(data[key])
        elif isinstance(data, list):
            for item in data:
                self._mask_sensitive(item)
    
    def _get_user_from_jwt(self, request):
        try:
            from rest_framework_simplejwt.authentication import JWTAuthentication
            
            jwt_auth = JWTAuthentication()
            result = jwt_auth.authenticate(request)
            
            if result is not None:
                user, token = result
                return user.id, user.username
            
            return None, None
        except Exception:
            return None, None
    
    def _get_client_ip(self, request) -> str:
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        if xff:
            return xff.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')