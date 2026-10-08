"""Authentication backends for Hydr8."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

if TYPE_CHECKING:
    from django.http import HttpRequest

    from apps.users.models import User

logger = logging.getLogger(__name__)


class EmailOrUsernameBackend(ModelBackend):
    """Authenticates against either username OR email (case-insensitive).

    Features:
      - Allows login via standard username (e.g., 'admin', 'jps2_cashier')
      - Allows login via email address (e.g., 'cashier@branch1.ph')
      - Enforces that soft-deleted users (deleted_at IS NOT NULL) are barred from login
      - Runs hasher on failed user lookup to mitigate timing side-channel attacks
    """

    def authenticate(
        self,
        request: HttpRequest | None = None,
        username: str | None = None,
        password: str | None = None,
        **kwargs,
    ) -> User | None:
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if not username or not password:
            return None

        clean_identifier = username.strip()

        # Look up by username or email (case-insensitive)
        user = (
            UserModel._default_manager.filter(
                Q(username__iexact=clean_identifier) | Q(email__iexact=clean_identifier),
                deleted_at__isnull=True,
            )
            .first()
        )

        if user is None:
            # Timing mitigation: run password hasher even if user not found
            UserModel().set_password(password)
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user

        return None
