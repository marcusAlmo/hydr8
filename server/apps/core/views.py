import logging
from typing import Any

from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

logger = logging.getLogger(__name__)


def error_message(exc: Exception) -> str:
    """Returns a single, human-readable string from any exception.

    For Django ``ValidationError`` the ``message`` or ``messages`` list
    is preferred, otherwise we fall back to ``str(exc)``.
    """
    if isinstance(exc, ValidationError):
        if hasattr(exc, "message"):
            return str(exc.message)
        if hasattr(exc, "messages"):
            return " ".join(str(m) for m in exc.messages)
    return str(exc)


def toast_response(
    request,
    message: str,
    type: str = "success",
    duration: int = 4000,
    status: int = 200,
) -> HttpResponse:
    """Renders the shared OOB toast partial for HTMX mutation endpoints."""
    return render(
        request,
        "components/toasts/toast.html",
        {
            "id": int(timezone.now().timestamp() * 1000),
            "message": message,
            "type": type,
            "duration": duration,
        },
        status=status,
    )


def toast_success(request, message: str, duration: int = 4000) -> HttpResponse:
    """Returns a success toast with the given message."""
    return toast_response(request, message, type="success", duration=duration)


def toast_error(
    request,
    message: str,
    duration: int = 6000,
    status: int = 400,
) -> HttpResponse:
    """Returns an error toast with the given message."""
    return toast_response(
        request, message, type="error", duration=duration, status=status
    )


def toast_for_exception(request, exc: Exception, status: int = 400) -> HttpResponse:
    """Returns an error toast parsed from a backend exception."""
    return toast_error(request, error_message(exc), status=status)


def handler404_view(request, exception=None):
    """Renders a friendly 404 page for both HTMX and full-page requests."""
    if request.headers.get("HX-Request") == "true":
        return render(request, "core/404_fragment.html", status=404)
    return render(request, "core/404.html", status=404)


def handler500_view(request):
    """Renders a friendly 500 page for both HTMX and full-page requests."""
    if request.headers.get("HX-Request") == "true":
        return render(request, "core/500_fragment.html", status=500)
    return render(request, "core/500.html", status=500)
