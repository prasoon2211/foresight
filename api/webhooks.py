import hashlib
import hmac
import json

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from orchestration.tasks import enqueue_run_orchestrator, enqueue_snapshot_build
from surfaces.github import process_webhook


@csrf_exempt
def github_webhook(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed."}, status=405)
    if not settings.GITHUB_WEBHOOK_SECRET:
        return JsonResponse({"detail": "GitHub webhooks are not configured."}, status=503)
    signature = request.headers.get("X-Hub-Signature-256", "")
    expected = (
        "sha256="
        + hmac.new(
            settings.GITHUB_WEBHOOK_SECRET.encode(),
            request.body,
            hashlib.sha256,
        ).hexdigest()
    )
    if not hmac.compare_digest(signature, expected):
        return JsonResponse({"detail": "Invalid webhook signature."}, status=401)
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"detail": "Invalid JSON payload."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"detail": "Invalid JSON payload."}, status=400)
    process_webhook(
        event=request.headers.get("X-GitHub-Event", ""),
        payload=payload,
        enqueue_run=enqueue_run_orchestrator,
        enqueue_snapshot=enqueue_snapshot_build,
    )
    return JsonResponse({"accepted": True}, status=202)
