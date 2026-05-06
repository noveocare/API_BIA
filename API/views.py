from datetime import date, datetime
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import render
from django.db import connection, connections
from django.http import HttpResponse, JsonResponse
import json
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authentication import TokenAuthentication
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import serializers
from API.models import UserViewPermission, Transco_API
from API.permissions import require_view_permission, HasViewPermission
from API.query_builder import QueryBuilder, FilterConfig, error_response


ENVIRONNEMENT_REQUIRED_FILTER = FilterConfig( 'ENVIRONNEMENT', required = True )
SIREN_FILTER = FilterConfig( 'SIREN' )
RAISON_SOCIALE_FILTER = FilterConfig( 'RAISON_SOCIALE', operator = 'LIKE' )
IDFENT_REQUIRED_FILTER = FilterConfig( 'IDFENT', required = True )
IDFCAT_REQUIRED_FILTER = FilterConfig( 'IDFCAT', required = True )


class MonTokenSerializer(TokenObtainPairSerializer):
    client_id = serializers.CharField()
    client_secret = serializers.CharField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop('username', None)
        self.fields.pop('password', None)

    @classmethod
    def get_token(cls, user):
        """
        Surcharge pour ajouter les permissions de vues dans le token JWT.
        """
        token = super().get_token(user)
        
        # Récupérer les vues autorisées pour cet utilisateur
        user_permissions = UserViewPermission.objects.filter(
            user=user,
            view_permission__is_active=True
        ).select_related('view_permission')
        
        # Ajouter la liste des codes de vues autorisées dans le payload du token
        token['allowed_views'] = [
            up.view_permission.code for up in user_permissions
        ]
        
        # Optionnel : ajouter aussi le username pour référence
        token['username'] = user.username
        
        return token

    def validate(self, attrs):
        # 1. Correspondance pour l'authentification
        attrs['username'] = attrs.get('client_id')
        attrs['password'] = attrs.get('client_secret')
        
        # 2. Appel de la logique parente pour générer access et refresh
        data = super().validate(attrs)

        # 3. Ajout de vos informations personnalisées
        data['token_type'] = "Bearer"
        data['expires_in'] = 3600  # Valeur en secondes (1h)
        
        # 4. Ajouter les vues autorisées dans la réponse (pour info client)
        user = self.user
        user_permissions = UserViewPermission.objects.filter(
            user=user,
            view_permission__is_active=True
        ).select_related('view_permission')
        
        data['allowed_views'] = [
            up.view_permission.code for up in user_permissions
        ]
        
        return data
auth_header = openapi.Parameter(
    'Authorization',
    openapi.IN_HEADER,
    description="Token d'authentification",
    type=openapi.TYPE_STRING,
    required=True,
    example="abcdef1234567890"
)
content_type_header = openapi.Parameter(
    'Content-Type',
    openapi.IN_HEADER,
    description="Type de contenu de la requête. Doit être 'application/json'",
    type=openapi.TYPE_STRING,
    default='application/json',
    required=True
)

def data_to_json(data):
    """Convertit une liste de dictionnaires en JSON."""
    def default_serializer(obj):
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        elif isinstance(obj, Decimal):
            return float(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    return json.dumps(data, default=default_serializer, ensure_ascii=False, indent=2)

def request_to_json(cursor):
    if cursor.description == None:
        data = None
        nbresult = 0
    else:
        
        # Obtenir les métadonnées des colonnes
        columns = [col[0] for col in cursor.description]
        print(cursor.description[0])
        print(columns)
        
        rows = cursor.fetchall()
        data = []
        for row in rows:
            if len(row) != len(columns):
                print(f"Avertissement : ligne avec {len(row)} éléments, attendu {len(columns)}")
                continue  # Ignorer les lignes mal formées
            row_dict = dict(zip(columns, row))
            data.append(row_dict)
        nbresult = len(rows)
    result = {"len":nbresult,"data":data}
    return HttpResponse(data_to_json(result), content_type='application/json')

class ExpiringTokenAuthentication(JWTAuthentication):
    keyword = 'Bearer'
    def authenticate(self, request):
        auth_header = request.headers.get('Authorization')
        if auth_header and not auth_header.startswith(self.keyword + ' '):
            token_value = auth_header.split(' ')[-1]
            new_header = f"{self.keyword} {token_value}"
            request.META['HTTP_AUTHORIZATION'] = new_header
        
        return super().authenticate(request)


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = MonTokenSerializer

    @swagger_auto_schema(
        operation_id='api-token',
        operation_summary="Authentification Client",
        # On définit manuellement le corps de la requête pour Swagger
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['client_id', 'client_secret'],
            properties={
                'client_id': openapi.Schema(type=openapi.TYPE_STRING, description="Identifiant client"),
                'client_secret': openapi.Schema(type=openapi.TYPE_STRING, description="Secret client"),
            },
        ),
        responses={
            200: openapi.Response(
                description="Jetons récupérés avec succès",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'refresh': openapi.Schema(type=openapi.TYPE_STRING),
                        'access': openapi.Schema(type=openapi.TYPE_STRING),
                        'token_type': openapi.Schema(type=openapi.TYPE_STRING),
                        'expires_in': openapi.Schema(type=openapi.TYPE_INTEGER),
                    },
                    example={
                        "access": "eyJhbGci...",
                        "refresh": "eyJhbGci...",
                        "token_type": "Bearer",
                        "expires_in": 3600
                    }
                ),
            ),
            401: openapi.Response(
                description="Aucun compte actif n'a été trouvé avec les identifiants fournis",
            ),
            500: openapi.Response(
                description="Erreur interne du serveur",
            ),
        }
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

class CustomTokenRefreshView(TokenRefreshView):
    @swagger_auto_schema(
        operation_id='api-token-refresh',
        operation_description="""Rafraîchit un **access token** expiré à l'aide d'un **refresh token** valide.
        - Le refresh token doit être valide et non expiré.
        - Retourne un nouvel access token valide 1h.
        """,
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'refresh': openapi.Schema(type=openapi.TYPE_STRING, description="Votre refresh token valide 2h.")
            }
        ),
        responses={
            200: openapi.Response(
                description="Jetons récupérés avec succès",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'refresh': openapi.Schema(type=openapi.TYPE_STRING, description="Token de rafraîchissement valable 2h"),
                        'access': openapi.Schema(type=openapi.TYPE_STRING, description="Token d'accès valable 1h"),
                    },
                    example={
                        "access": "votre_nouvel_access_token_ici"
                    }
                ),
            ),
            401: openapi.Response(
                description="Token invalide ou expiré",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'detail': openapi.Schema(type=openapi.TYPE_STRING, description="Détail de l'erreur"),
                        'code': openapi.Schema(type=openapi.TYPE_STRING, description="Code de l'erreur"),
                    },
                    example={
                        "detail": "Token is invalid",
                        "code": "token_not_valid"
                    }
                )
            ),
            500: openapi.Response(
                description="Erreur interne du serveur",
            ),
        }
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

class TokenRevokeView(APIView):
    @swagger_auto_schema(
        operation_id='auth_logout',
        operation_summary="Révoquer un accès",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['refresh'],
            properties={
                'refresh': openapi.Schema(type=openapi.TYPE_STRING, description="Le refresh token à révoquer")
            }
        ),
        responses={205: "Token révoqué avec succès", 400: "Token invalide"}
    )
    def post(self, request):
        try:
            refresh_token = request.data["refresh"]
            token = RefreshToken(refresh_token)
            token.blacklist() # Ajoute le token à la table OutstandingToken
            return Response({"message": "Successfully logged out."}, status=status.HTTP_205_RESET_CONTENT)
        except Exception:
            return Response({"error": "Invalid token."}, status=status.HTTP_400_BAD_REQUEST)

def get_connections(nom_api, groups):
    transco = Transco_API.objects.filter(NOM_API = nom_api, CLIENT= groups.first().name).first()
    connection_string = f"[{transco.SCHEMA}].VIEW_{transco.NOM_TABLE}"
    print(connection_string)
    return transco, connection_string

@swagger_auto_schema(
    operation_id = 'liste-entreprises',
    method = 'post',
    tags = [ 'Start&Go' ],
    manual_parameters = [ auth_header, content_type_header, openapi.Parameter( 'limit', openapi.IN_QUERY, description = "Nombre maximal d'éléments à retourner", type = openapi.TYPE_INTEGER, default = 10 ), ],
    request_body = openapi.Schema(
        type = openapi.TYPE_OBJECT,
        required = [ 'data' ],
        title="Critères de recherche",
        properties = {
            'data': openapi.Schema(
                type = openapi.TYPE_OBJECT,
                properties = {
                    'ENVIRONNEMENT' : openapi.Schema(
                        type = openapi.TYPE_STRING,
                        description = "Nom de l\'Environnement \n Length : 4 - 10",
                    ),
                    'SIREN' : openapi.Schema(
                        type = openapi.TYPE_STRING,
                        description = 'Numéro de SIREN \n Length : 9'
                    ),
                    'RAISON_SOCIALE' : openapi.Schema(
                        type = openapi.TYPE_STRING,
                        description = 'Raison Sociale \n Length : 5 - 50'
                    ),

                },
                required = [ 'ENVIRONNEMENT' ]
            )
        }
    ),
    responses={
        200: openapi.Response(
            description="Succès",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                title="Résultat",
                properties={
                    'len': openapi.Schema(type=openapi.TYPE_INTEGER, description='Nombre de résultats'),
                    'data': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'DATE_API' : openapi.Schema( type = openapi.TYPE_STRING, description = 'Date de Mise à Jour de la Route \n Format : \'YYYY-MM-DD\'' ),
                                'DATE_OPEN' : openapi.Schema( type = openapi.TYPE_STRING, description = 'Date des Données Sources OPEN \n Format : \'YYYY-MM-DD\'' ),
                                'ENVIRONNEMENT' : openapi.Schema( type = openapi.TYPE_STRING, description = 'Nom de l\'Environnement \n Length : 4 - 10' ),
                                'IDFENT' : openapi.Schema( type = openapi.TYPE_INTEGER, description = 'Identifiant OPEN de l\'Entreprise \n Format : integer' ),
                                'SIREN' : openapi.Schema( type = openapi.TYPE_STRING, description = 'Numéro de SIREN \n Length : 9' ),
                                'SIRET' : openapi.Schema( type = openapi.TYPE_STRING, description = 'SIRET de l\'Entreprise \n Length : 14' ),
                                'RAISON_SOCIALE' : openapi.Schema( type = openapi.TYPE_STRING, description = 'Raison Sociale \n Length : 5 - 50' ),
                            }
                        ),
                        description='Liste des Résultats'
                    ),
                },
                example={
                    "len": 2,
                    "data": [
                            {
                              "DATE_API": "2026-05-12",
                              "DATE_OPEN": "2026-05-10",
                              "ENVIRONNEMENT": "ENV1",
                              "IDFENT": 1000000022,
                              "SIREN": "123456789",
                              "SIRET": "12345678900097",
                              "RAISON_SOCIALE": "XXXXXXXXX"
                            },
                            {
                              "DATE_API": "2026-05-12",
                              "DATE_OPEN": "2026-05-10",
                              "ENVIRONNEMENT": "ENV1",
                              "IDFENT": 1000000023,
                              "SIREN": "123456789",
                              "SIRET": "12345678900055",
                              "RAISON_SOCIALE": "XXXXXXXXX XXXXXXX"
                            }
                    ]
                }
            )
        ),
        400: openapi.Response(
            description="Requête invalide",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'status': openapi.Schema(type=openapi.TYPE_STRING, description='Statut de l\'erreur'),
                    'message': openapi.Schema(type=openapi.TYPE_STRING, description='Message d\'erreur')
                },
                example={
                    'status': 'error',
                    'message': 'Corps de requête invalide: JSON attendu'
                }
            )
        ),
        500: openapi.Response(
            description="Erreur serveur",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'status': openapi.Schema(type=openapi.TYPE_STRING, description='Statut de l\'erreur'),
                    'message': openapi.Schema(type=openapi.TYPE_STRING, description='Message d\'erreur')
                },
                example={
                    'status': 'error',
                    'message': 'Erreur lors de l\'exécution de la requête'
                }
            )
        ),
    },
    operation_description="""
        Récupère les entreprises avec un contrat ouvert qui existent sur l'environnement.
        Les entreprises peuvent être filtrées avec : 
        - Un SIREN.
        - Une RAISON_SOCIALE, il est possible de renseigner un mot-clé d'au moins 5 caractères, et les entreprises correspondantes seront retournées.
        
        Les données sont mises à jour à J-2, et récupèrent les entreprises avec un contrat Santé ouvert entre J-2 et J.
        
        Règles :
        - Il faut obligatoirement un ENVIRONNEMENT.
        - Il faut renseigner soit un SIREN soit une RAISON_SOCIALE.
        - La donnée DATE_API, permet de savoir de quand date la dernière mise à jour des données de la route.
        - La donnée DATE_OPEN, permet de connaître l'antériorité des données OPEN remontées, elle sera au minimum à J-2 par rapport DATE_API.
    """,
    operation_summary = "Obtenir les entreprises qui existent sur un environnement"
)
@api_view(['POST'])
@authentication_classes([ExpiringTokenAuthentication])
@require_view_permission('startgo.liste_entreprises')
@permission_classes([HasViewPermission])
def liste_entreprises(request):
    try:
        groups = request.user.groups
        transco, connection_string = get_connections( 'SGO_Liste_Entreprises', groups )
        
        builder = QueryBuilder(
            connection_string=connection_string,
            filters = [ ENVIRONNEMENT_REQUIRED_FILTER, SIREN_FILTER, RAISON_SOCIALE_FILTER ],
        )
        return builder.execute(request, transco, request_to_json)
    except Exception as e:
        return HttpResponse(f"Erreur : {str(e)}", status=500)




@swagger_auto_schema(
    operation_id = 'liste-categories',
    method = 'post',
    tags = [ 'Start&Go' ],
    manual_parameters = [ auth_header, content_type_header, openapi.Parameter( 'limit', openapi.IN_QUERY, description = "Nombre maximal d'éléments à retourner", type = openapi.TYPE_INTEGER, default = 10 ), ],
    request_body = openapi.Schema(
        type = openapi.TYPE_OBJECT,
        required = [ 'data' ],
        title="Critères de recherche",
        properties = {
            'data': openapi.Schema(
                type = openapi.TYPE_OBJECT,
                properties = {
                    'ENVIRONNEMENT' : openapi.Schema(
                        type = openapi.TYPE_STRING,
                        description = "Nom de l\'Environnement \n Length : 4 - 10",
                    ),
                    'IDFENT' : openapi.Schema(
                        type = openapi.TYPE_INTEGER,
                        description = 'Identifiant OPEN de l\'Entreprise \n Format : integer'
                    ),

                },
                required = [ 'ENVIRONNEMENT', 'IDFENT' ]
            )
        }
    ),
    responses={
        200: openapi.Response(
            description="Succès",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                title="Résultat",
                properties={
                    'len': openapi.Schema(type=openapi.TYPE_INTEGER, description='Nombre de résultats'),
                    'data': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'DATE_API' : openapi.Schema( type = openapi.TYPE_STRING, description = 'Date de Mise à Jour de la Route \n Format : \'YYYY-MM-DD\'' ),
                                'DATE_OPEN' : openapi.Schema( type = openapi.TYPE_STRING, description = 'Date des Données Sources OPEN \n Format : \'YYYY-MM-DD\'' ),
                                'ENVIRONNEMENT' : openapi.Schema( type = openapi.TYPE_STRING, description = 'Nom de l\'Environnement \n Length : 4 - 10' ),
                                'IDFENT' : openapi.Schema( type = openapi.TYPE_INTEGER, description = 'Identifiant OPEN de l\'Entreprise \n Format : integer' ),
                                'IDFCAT' : openapi.Schema( type = openapi.TYPE_STRING, description = 'Identifiant OPEN de la Catégorie \n Length : 2' ),
                                'LIBELLE_CATEGORIE' : openapi.Schema( type = openapi.TYPE_STRING, description = 'Libellé de la Catégorie \n Length : 3 - 50' ),
                            }
                        ),
                        description='Liste des Résultats'
                    ),
                },
                example={
                    "len": 2,
                    "data": [
                            {
                              "DATE_API": "2026-05-12",
                              "DATE_OPEN": "2026-05-10",
                              "ENVIRONNEMENT": "ENV1",
                              "IDFENT": 1000013463,
                              "IDFCAT": "10",
                              "LIBELLE_CATEGORIE": "NON CADRES"
                            },
                            {
                              "DATE_API": "2026-05-12",
                              "DATE_OPEN": "2026-05-10",
                              "ENVIRONNEMENT": "ENV1",
                              "IDFENT": 1000013463,
                              "IDFCAT": "20",
                              "LIBELLE_CATEGORIE": "CADRES"
                            }
                    ]
                }
            )
        ),
        400: openapi.Response(
            description="Requête invalide",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'status': openapi.Schema(type=openapi.TYPE_STRING, description='Statut de l\'erreur'),
                    'message': openapi.Schema(type=openapi.TYPE_STRING, description='Message d\'erreur')
                },
                example={
                    'status': 'error',
                    'message': 'Corps de requête invalide: JSON attendu'
                }
            )
        ),
        500: openapi.Response(
            description="Erreur serveur",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'status': openapi.Schema(type=openapi.TYPE_STRING, description='Statut de l\'erreur'),
                    'message': openapi.Schema(type=openapi.TYPE_STRING, description='Message d\'erreur')
                },
                example={
                    'status': 'error',
                    'message': 'Erreur lors de l\'exécution de la requête'
                }
            )
        ),
    },
    operation_description="""
        Récupère les catégories Santé qui existent et sont ouvertes pour une entreprise.
        
        Les données sont mises à jour à J-2, et récupèrent les entreprises avec un contrat Santé ouvert entre J-2 et J.
        
        Règles :
        - Il faut obligatoirement un ENVIRONNEMENT et un IDFENT.
        - La donnée DATE_API, permet de savoir de quand date la dernière mise à jour des données de la route.
        - La donnée DATE_OPEN, permet de connaître l'antériorité des données OPEN remontées, elle sera au minimum à J-2 par rapport DATE_API.
    """,
    operation_summary = "Obtenir les catégories qui existent sur une entreprise"
)
@api_view(['POST'])
@authentication_classes([ExpiringTokenAuthentication])
@require_view_permission('startgo.liste_categories')
@permission_classes([HasViewPermission])
def liste_categories(request):
    try:
        groups = request.user.groups
        transco, connection_string = get_connections( 'SGO_Liste_Categories', groups )
        
        builder = QueryBuilder(
            connection_string=connection_string,
            filters = [ ENVIRONNEMENT_REQUIRED_FILTER, IDFENT_REQUIRED_FILTER ],
        )
        return builder.execute(request, transco, request_to_json)
    except Exception as e:
        return HttpResponse(f"Erreur : {str(e)}", status=500)





@swagger_auto_schema(
    operation_id = 'liste-contrats',
    method = 'post',
    tags = [ 'Start&Go' ],
    manual_parameters = [ auth_header, content_type_header, openapi.Parameter( 'limit', openapi.IN_QUERY, description = "Nombre maximal d'éléments à retourner", type = openapi.TYPE_INTEGER, default = 10 ), ],
    request_body = openapi.Schema(
        type = openapi.TYPE_OBJECT,
        required = [ 'data' ],
        title="Critères de recherche",
        properties = {
            'data': openapi.Schema(
                type = openapi.TYPE_OBJECT,
                properties = {
                    'ENVIRONNEMENT' : openapi.Schema(
                        type = openapi.TYPE_STRING,
                        description = "Nom de l\'Environnement \n Length : 4 - 10",
                    ),
                    'IDFENT' : openapi.Schema(
                        type = openapi.TYPE_INTEGER,
                        description = 'Identifiant OPEN de l\'Entreprise \n Format : integer'
                    ),
                    'IDFCAT' : openapi.Schema(
                        type = openapi.TYPE_STRING,
                        description = 'Identifiant OPEN de la Catégorie \n Length : 2'
                    ),

                },
                required = [ 'ENVIRONNEMENT', 'IDFENT', 'IDFCAT' ]
            )
        }
    ),
    responses={
        200: openapi.Response(
            description="Succès",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                title="Résultat",
                properties={
                    'len': openapi.Schema(type=openapi.TYPE_INTEGER, description='Nombre de résultats'),
                    'data': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'DATE_API' : openapi.Schema( type = openapi.TYPE_STRING, description = 'Date de Mise à Jour de la Route \n Format : \'YYYY-MM-DD\'' ),
                                'DATE_OPEN' : openapi.Schema( type = openapi.TYPE_STRING, description = 'Date des Données Sources OPEN \n Format : \'YYYY-MM-DD\'' ),
                                'ENVIRONNEMENT' : openapi.Schema( type = openapi.TYPE_STRING, description = 'Nom de l\'Environnement \n Length : 4 - 10' ),
                                'IDFENT' : openapi.Schema( type = openapi.TYPE_INTEGER, description = 'Identifiant OPEN de l\'Entreprise \n Format : integer' ),
                                'IDFCAT' : openapi.Schema( type = openapi.TYPE_STRING, description = 'Identifiant OPEN de la Catégorie \n Length : 2' ),
                                'TYPE_POLICE' : openapi.Schema( type = openapi.TYPE_STRING, description = 'Type de Police \n Length : 4 - 20' ),
                                'NUMERO_POLICE' : openapi.Schema( type = openapi.TYPE_STRING, description = 'Numéro de Police \n Length : 0 - 15' ),
                                'RISQUE' : openapi.Schema( type = openapi.TYPE_STRING, description = 'Risque \n Length : 5 - 30' ),
                                'PRODUIT' : openapi.Schema( type = openapi.TYPE_INTEGER, description = 'Numéro de Produit \n Format : integer' ),
                                'LIB_INTERNE_PRODUIT' : openapi.Schema( type = openapi.TYPE_STRING, description = 'Libellé du Produit \n Length : 5 - 32' ),
                                'LIBELLE_FACU' : openapi.Schema( type = openapi.TYPE_STRING, description = 'Libellé Facu \n Length : 0 - 50' ),
                            }
                        ),
                        description='Liste des Résultats'
                    ),
                },
                example={
                    "len": 2,
                    "data": [
                            {
                              "DATE_API": "2026-05-12",
                              "DATE_OPEN": "2026-05-10",
                              "ENVIRONNEMENT": "ENV1",
                              "IDFENT": 1000013463,
                              "IDFCAT": "10",
                              "TYPE_POLICE": "BASE",
                              "NUMERO_POLICE": "09910002803",
                              "RISQUE": "MALADIE",
                              "PRODUIT": 61401,
                              "LIB_INTERNE_PRODUIT": "XXXXX XXXXXXXX NC BASE",
                              "LIBELLE_FACU": "BASE"
                            },
                            {
                              "DATE_API": "2026-05-12",
                              "DATE_OPEN": "2026-05-10",
                              "ENVIRONNEMENT": "ENV1",
                              "IDFENT": 1000013463,
                              "IDFCAT": "10",
                              "TYPE_POLICE": "BASE",
                              "NUMERO_POLICE": "09910002804",
                              "RISQUE": "MALADIE",
                              "PRODUIT": 89856,
                              "LIB_INTERNE_PRODUIT": "XXXXX XXXXXXXX NC BASE NIV 1",
                              "LIBELLE_FACU": "BASE"
                            },
                            {
                              "DATE_API": "2026-05-12",
                              "DATE_OPEN": "2026-05-10",
                              "ENVIRONNEMENT": "ENV1",
                              "IDFENT": 1000013463,
                              "IDFCAT": "10",
                              "TYPE_POLICE": "CHOIX INDIVIDUEL",
                              "NUMERO_POLICE": "09920002803",
                              "RISQUE": "MALADIE",
                              "PRODUIT": 224259,
                              "LIB_INTERNE_PRODUIT": "XXXXX XXXXXXXX NC OPT 1",
                              "LIBELLE_FACU": "OPTION 1"
                            }
                    ]
                }
            )
        ),
        400: openapi.Response(
            description="Requête invalide",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'status': openapi.Schema(type=openapi.TYPE_STRING, description='Statut de l\'erreur'),
                    'message': openapi.Schema(type=openapi.TYPE_STRING, description='Message d\'erreur')
                },
                example={
                    'status': 'error',
                    'message': 'Corps de requête invalide: JSON attendu'
                }
            )
        ),
        500: openapi.Response(
            description="Erreur serveur",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'status': openapi.Schema(type=openapi.TYPE_STRING, description='Statut de l\'erreur'),
                    'message': openapi.Schema(type=openapi.TYPE_STRING, description='Message d\'erreur')
                },
                example={
                    'status': 'error',
                    'message': 'Erreur lors de l\'exécution de la requête'
                }
            )
        ),
    },
    operation_description="""
        Récupère les contrats Santé qui existent et sont ouverts pour une entreprise et une catégorie.
        
        Les données sont mises à jour à J-2, et récupèrent les entreprises avec un contrat Santé ouvert entre J-2 et J.
        
        Règles :
        - Il faut obligatoirement un ENVIRONNEMENT, un IDFENT et un IDFCAT.
        - La donnée DATE_API, permet de savoir de quand date la dernière mise à jour des données de la route.
        - La donnée DATE_OPEN, permet de connaître l'antériorité des données OPEN remontées, elle sera au minimum à J-2 par rapport DATE_API.
    """,
    operation_summary = "Obtenir les contrats qui existent sur une entreprise et une catégorie"
)
@api_view(['POST'])
@authentication_classes([ExpiringTokenAuthentication])
@require_view_permission('startgo.liste_contrats')
@permission_classes([HasViewPermission])
def liste_contrats(request):
    try:
        groups = request.user.groups
        transco, connection_string = get_connections( 'SGO_Liste_Contrats', groups )
        
        builder = QueryBuilder(
            connection_string=connection_string,
            filters = [ ENVIRONNEMENT_REQUIRED_FILTER, IDFENT_REQUIRED_FILTER, IDFCAT_REQUIRED_FILTER ],
        )
        return builder.execute(request, transco, request_to_json)
    except Exception as e:
        return HttpResponse(f"Erreur : {str(e)}", status=500)

