from django.urls import include, path

from api import api

urlpatterns = [
    path("_allauth/", include("allauth.headless.urls")),
    path("api/", api.urls),
]
