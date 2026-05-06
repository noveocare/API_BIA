"""
URL configuration for API_DATA_BO project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from API import views
from django.urls import path, include
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

schema_view = get_schema_view(
    openapi.Info(
        title="API Data - Données Start&Go",
        default_version='v1',
        description="API permettant la récupération de données OPEN nécessaires pour compléter un Start&Go.",
        contact=openapi.Contact(email="ld.data.analysts@noveocare.com"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path('v1/01/liste-entreprises/', views.liste_entreprises, name='liste-entreprises'),
    path('v1/02/liste-categories/', views.liste_categories, name='liste-categories'),
    path('v1/03/liste-contrats/', views.liste_contrats, name='liste-contrats'),
    
    path('api/token/', views.CustomTokenObtainPairView.as_view(), name='token-obtain-pair'),
    path('api/token/refresh/', views.CustomTokenRefreshView.as_view(), name='token-refresh'),
    path('api/token/revoke/', views.TokenRevokeView.as_view(), name='token-revoke'),

    path('admin/', admin.site.urls),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]
