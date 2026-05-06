"""
Module utilitaire pour la construction et l'exécution de requêtes SQL.
Mutualise toute la logique répétitive des vues API.
"""
from django.http import JsonResponse, HttpResponse
from django.db import connections
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
import json


def error_response(message: str, status: int = 400) -> JsonResponse:
    """Crée une réponse d'erreur standardisée."""
    return JsonResponse({'status': 'error', 'message': message}, status=status)


@dataclass
class FilterConfig:
    """Configuration d'un filtre de requête."""
    field_name: str                    # Nom du champ en BDD (ex: 'SIRET', 'PERIODE')
    param_name: str = None             # Nom du param dans request_data (par défaut = field_name)
    is_list: bool = False              # True si c'est une liste (IN clause)
    required: bool = False             # True si le paramètre est obligatoire
    max_items: int = None              # Limite max pour les listes (ex: 25 pour SIRET)
    operator: str = '='                # Opérateur SQL (=, <=, >=, <, >, !=)
    
    def __post_init__(self):
        if self.param_name is None:
            self.param_name = self.field_name


@dataclass
class QueryBuilder:
    """
    Constructeur de requêtes SQL avec gestion des filtres dynamiques.
    
    Usage:
        builder = QueryBuilder(
            connection_string="[SCHEMA].VIEW_TABLE",
            filters=[
                FilterConfig('SIRET', is_list=True, required=True, max_items=25),
                FilterConfig('PERIODE'),
                FilterConfig('NUMERO_SINISTRE'),
            ]
        )
        result = builder.execute(request, transco)
    """
    connection_string: str
    filters: List[FilterConfig] = field(default_factory=list)
    
    def parse_request(self, request) -> Tuple[Optional[Dict], Optional[int], Optional[JsonResponse]]:
        """
        Parse la requête : body JSON et paramètre limit.
        Retourne (request_data, limit, error_response)
        """
        # Parse limit
        limit = None
        limit_str = request.query_params.get('limit')
        if limit_str:
            try:
                limit = int(limit_str)
            except ValueError:
                return None, None, JsonResponse({'error': 'Invalid limit'}, status=400)
        
        # Parse body JSON
        try:
            request_data = json.loads(request.body)
            request_data = request_data.get('data', {})
        except json.JSONDecodeError:
            return None, None, error_response('Corps de requête invalide: JSON attendu')
        
        return request_data, limit, None
    
    def validate_filters(self, request_data: Dict) -> Tuple[Dict[str, Any], Optional[JsonResponse]]:
        """
        Valide et extrait les valeurs des filtres depuis request_data.
        Retourne (validated_values, error_response)
        """
        values = {}
        
        for filter_cfg in self.filters:
            value = request_data.get(filter_cfg.param_name)
            
            # Vérification required
            if filter_cfg.required:
                if value is None:
                    return None, error_response(f'Corps de requête invalide: Aucun {filter_cfg.param_name}')
                if filter_cfg.is_list and len(value) == 0:
                    return None, error_response(f'Corps de requête invalide: Aucun {filter_cfg.param_name}')
            
            # Vérification max_items pour les listes
            if filter_cfg.is_list and filter_cfg.max_items and value:
                if len(value) > filter_cfg.max_items:
                    return None, error_response(
                        f'Corps de requête invalide: Nombre de {filter_cfg.param_name} max dépassé ({filter_cfg.max_items})'
                    )
            
            ## Vérification Longueur du LIKE
            if filter_cfg.operator == 'LIKE' and filter_cfg.field_name == 'RAISON_SOCIALE' and value is not None:
                if len( value ) < 5:
                    return None, error_response( f'Corps de requête invalide: Le filtre sur { filter_cfg.field_name } doit être d\'au moins 5 caractères.' )
                if '%' in value:
                    return None, error_response( f'Corps de requête invalide: Le filtre sur { filter_cfg.field_name } contient un caractère non valide.' )
            
            values[filter_cfg.field_name] = value
         
        
        ## Vérification Présence de SIREN ou de RAISON_SOCIALE
        if 'SIREN' in values and 'RAISON_SOCIALE' in values and values['SIREN'] is None and values['RAISON_SOCIALE'] is None:
            return None, error_response( f'Corps de requête invalide: Il faut obligatoirement un des deux filtres (SIREN, RAISON_SOCIALE)' )
        
        return values, None
    
    def build_query(self, limit: Optional[int], filter_values: Dict[str, Any]) -> Tuple[str, List]:
        """
        Construit la requête SQL avec les filtres.
        Retourne (query_string, params_list)
        """
        query = "SELECT "
        if limit is not None:
            query += f"TOP ({limit}) "
        query += f"* FROM {self.connection_string} WHERE 1 = 1"
        
        params = []
        
        for filter_cfg in self.filters:
            value = filter_values.get(filter_cfg.field_name)
            
            if value is None or value == '':
                continue
                
            if filter_cfg.is_list:
                if len(value) > 0:
                    placeholders = ", ".join(["%s"] * len(value))
                    query += f" AND {filter_cfg.field_name} IN ({placeholders})"
                    params.extend(value)
            elif filter_cfg.operator == 'LIKE':
                query += f" AND { filter_cfg.field_name } like %s"
                params.append( f"%{ value }%" )
            else:
                query += f" AND {filter_cfg.field_name} {filter_cfg.operator} %s"
                params.append( value )
        
        return query, params
    
    def execute(self, request, transco, request_to_json_func) -> HttpResponse:
        """
        Exécute la requête complète : parse, valide, construit, exécute.
        
        Args:
            request: La requête HTTP Django
            transco: L'objet Transco_API pour la connexion
            request_to_json_func: La fonction pour convertir le cursor en JSON
        
        Returns:
            HttpResponse avec le résultat ou l'erreur
        """
        # 1. Parse request
        request_data, limit, error = self.parse_request(request)
        if error:
            return error
        
        # 2. Validate filters
        filter_values, error = self.validate_filters(request_data)
        if error:
            return error
        
        # 3. Build query
        query, params = self.build_query(limit, filter_values)
        # 4. Execute query
        try:
            with connections[transco.SCHEMA].cursor() as cursor:
                print(transco.SCHEMA)
                cursor.execute(query, params)
                print(cursor)
                return request_to_json_func(cursor)
        except Exception as e:
            print(f"Erreur interne lors de l'exécution de la requête: {e}")
            return error_response("Erreur lors de l'exécution de la requête", status=500)