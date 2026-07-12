from django.urls import include, path

from api import api
from api.webhooks import github_webhook

urlpatterns = [
    path("_allauth/", include("allauth.headless.urls")),
    path("api/webhooks/github", github_webhook),
    path("api/", api.urls),
]
