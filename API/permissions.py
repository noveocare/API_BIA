from rest_framework.permissions import BasePermission
from rest_framework_simplejwt.authentication import JWTAuthentication
from functools import wraps
from django.http import JsonResponse
import re


class HasViewPermission(BasePermission):
    """
    Permission qui vérifie si l'utilisateur a accès à la vue demandée.
    Les permissions sont lues directement depuis le token JWT,
    donc aucun accès à la base de données n'est nécessaire.
    """
    
    def has_permission(self, request, view):
        # Récupérer le code de permission requis pour cette vue
        required_code = view.__class__.__name__ 
        if required_code == ('SchemaView'):
            return True
        if required_code is None:
            return False
        if 'api' in required_code:
            return True
        
        # Extraire les permissions du token JWT
        allowed_views = None
        if request.auth:
            allowed_views = request.auth.payload.get('allowed_views')
        if allowed_views is None:
            return False
        
        # Vérifier si la vue est autorisée
        for allowed in allowed_views:
            if allowed == '*':  # Super admin
                return True
            if required_code in allowed:
                return True
            # Support regex/wildcard
            if allowed.endswith('.*'):
                prefix = allowed[:-2]
                if required_code.startswith(prefix):
                    return True
        
        return False
    
    def _get_allowed_views_from_token(self, request):
        """
        Extrait les vues autorisées directement depuis le token JWT.
        Aucun accès à la base de données.
        """
        try:
            auth = JWTAuthentication()
            validated_token = auth.get_validated_token(
                auth.get_raw_token(auth.get_header(request))
            )
            return validated_token.get('allowed_views', [])
        except Exception:
            return None


def require_view_permission(permission_code):
    """
    Décorateur pour vérifier les permissions de vue.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            # Extraire les permissions du token
            try:
                auth = JWTAuthentication()
                validated_token = auth.get_validated_token(
                    auth.get_raw_token(auth.get_header(request))
                )
                allowed_views = validated_token.get('allowed_views', [])
            except Exception:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Token invalide ou expiré.'
                }, status=401)
            
            # Vérifier la permission
            has_access = False
            for allowed in allowed_views:
                if allowed == '*':
                    has_access = True
                    break
                if allowed == permission_code:
                    has_access = True
                    break
                if allowed.endswith('.*'):
                    prefix = allowed[:-2]
                    if permission_code.startswith(prefix):
                        has_access = True
                        break
            
            if not has_access:
                return JsonResponse({
                    'status': 'error',
                    'message': f"Permission refusée. Vous n'avez pas accès à '{permission_code}'."
                }, status=403)
            
            return view_func(request, *args, **kwargs)
        return wrapped_view
    return decorator