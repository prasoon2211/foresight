import os
from typing import cast

from asgiref.typing import ASGI3Application
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "foresight.settings")

django_application = get_asgi_application()

from api.terminal_proxy import ForesightAsgiApplication  # noqa: E402

application = ForesightAsgiApplication(cast(ASGI3Application, django_application))
