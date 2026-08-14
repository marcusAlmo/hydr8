"""
Role-based authorization helpers for Hydr8.

The ``Role`` model (apps.users.models.Role) is the single source of truth for
what a user may do inside the application, because it is the only authorization
surface that is editable through the UI (Employees & Users directory → Roles).

Django's ``is_staff`` flag is intentionally NOT consulted here. It is a
parallel boolean that drifts out of sync with the Role whenever a user is
created outside ``apps.users.services.create_user_account`` (e.g. via the
Django admin, a shell, or a fixture). Treating it as authoritative caused the
login bug where a Staff-role user with ``is_staff=False`` was rejected.

``is_superuser`` is kept as a platform-level escape hatch only. Platform
superusers have no ``company`` and no ``role`` (they sit above all tenants),
so without this bypass they would be locked out of every gate. It is not a
business role and is never assigned through the UI.

Canonical role names are defined in
``apps/users/migrations/0008_default_roles_and_permissions.py`` and mirrored
here. If a new back-office role is added, update ``_BACK_OFFICE_ROLE_NAMES``.
"""

# Mirrors CANONICAL_ROLES in migration 0008_default_roles_and_permissions.
ADMIN_ROLE_NAME = "Admin"
STAFF_ROLE_NAME = "Staff"
DRIVER_ROLE_NAME = "Driver"

_BACK_OFFICE_ROLE_NAMES = frozenset({ADMIN_ROLE_NAME, STAFF_ROLE_NAME})


def _role_name(user) -> str | None:
    """Returns the user's role name, or None if they have no role."""
    role = getattr(user, "role", None)
    return role.name if role is not None else None


def is_superuser(user) -> bool:
    """True for platform superusers (the infrastructure-level bypass)."""
    return bool(getattr(user, "is_superuser", False))


def is_back_office(user) -> bool:
    """
    True if the user may access the back-office system at all.

    Back-office roles: Admin, Staff. Drivers are excluded.
    Platform superusers always pass (no role row, but full platform access).
    """
    if not user.is_authenticated:
        return False
    if is_superuser(user):
        return True
    return _role_name(user) in _BACK_OFFICE_ROLE_NAMES


def is_admin(user) -> bool:
    """
    True if the user may perform administrator-only operations.

    This covers: editing system/company settings, and creating/changing/
    deleting other users. Per the role permission seed, only the Admin role
    grants Users-module write access; Staff explicitly does not.

    Platform superusers always pass.
    """
    if not user.is_authenticated:
        return False
    if is_superuser(user):
        return True
    return _role_name(user) == ADMIN_ROLE_NAME


def is_staff_role(user) -> bool:
    """
    True if the user has the **Staff** role specifically.

    Unlike ``is_back_office`` (which is True for both Admin and Staff), this
    helper returns ``True`` ONLY for the Staff role — never for Admin or
    platform superusers. Use it to apply Staff-specific restrictions (limited
    navigation, no dashboard/charts, settings profile-only).

    Staff users get a focused view of the system: the Add Remittance page
    (draft + create), full Customers access, and their own Profile in Settings.
    Everything else (Dashboard, Remittance History, Products, Employees, Audit
    Log, System Config, Company settings) is restricted to Admin.
    """
    if not user.is_authenticated:
        return False
    if is_superuser(user):
        return False
    return _role_name(user) == STAFF_ROLE_NAME
