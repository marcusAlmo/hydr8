import logging
from django.contrib.auth import logout as django_logout
from apps.core.models import AuditLog

# 1. Initialize the Python logger for this module
logger = logging.getLogger(__name__)


def custom_logout(request, is_system_initiated=False):
    # 2. Capture the user object BEFORE logging them out
    user = request.user

    # 3. Perform the actual Django logout (aliased to avoid recursion)
    django_logout(request)

    # 4. Safely attempt to create the Audit Log
    if user.is_authenticated:
        try:
            AuditLog.objects.create(
                action=AuditLog.Action.LOGOUT,  # Using the Enum instead of a raw string
                details=f"User {user.username} logged out of the system.",
                initiated_by=user if not is_system_initiated else None,
            )
        except Exception as e:
            # 5. Log the exception if the database insert fails
            logger.error(f"Failed to create logout AuditLog for user {user.username}: {e}", exc_info=True)
