import json
import logging
from datetime import datetime, timedelta

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mock data — Audit Log page
#
# Mirrors the django-auditlog LogEntry schema as used by Monito HR unofficial:
#   - action:        0=CREATE, 1=UPDATE, 2=DELETE, 3=ACCESS
#   - changes:       JSON dict {field: [old_value, new_value]}
#   - serialized_data: full snapshot of the object at log time
#   - remote_addr:   IP captured from X-Forwarded-For / REMOTE_ADDR
#   - cid:           Correlation ID (from CorrelationIdMiddleware)
#   - actor:         The user who performed the action
#   - object_repr:   str() of the affected object
#   - content_type:  "app_label.model_name"
#
# The login-capture design from Monito HR's UserDeviceSession is reflected
# in the mock entries: login/logout events include device_name, ip_address,
# and session_key in additional_data, exactly as the real UserDeviceSession
# model would record them.
#
# When real backend services are ready, swap ``_mock_audit_logs`` for a
# selector that queries ``auditlog.models.LogEntry`` with the same context
# shape — the templates already consume these keys.
# ---------------------------------------------------------------------------

_ACTION_LABELS = {0: "CREATE", 1: "UPDATE", 2: "DELETE", 3: "ACCESS"}

_ACTION_BADGE_CLASSES = {
    0: "bg-tertiary-container/20 text-tertiary border-tertiary/30",
    1: "bg-primary/10 text-primary border-primary/30",
    2: "bg-error/10 text-error border-error/30",
    3: "bg-[#D97706]/15 text-[#D97706] border-[#D97706]/30",
}


def _mock_audit_logs() -> list[dict]:
    """
    Mock audit log entries mirroring django-auditlog LogEntry fields.

    Includes a mix of CREATE/UPDATE/DELETE/ACCESS actions across Hydr8
    domain models (Customer, Remittance, Product, User, Settings), plus
    login/logout session events that mirror the UserDeviceSession capture
    design from Monito HR unofficial.
    """
    now = datetime.now()

    def ts(minutes_ago: int) -> str:
        return (now - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%d %H:%M:%S")

    return [
        # --- Login / Session events (UserDeviceSession capture design) ---
        {
            "id": 1,
            "timestamp": ts(3),
            "action": 3,
            "action_label": "ACCESS",
            "actor": "adrian.thorne",
            "actor_display": "Adrian Thorne",
            "actor_email": "adrian.thorne@hydr8-hq.io",
            "content_type": "users.User",
            "object_pk": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "object_repr": "Adrian Thorne (adrian.thorne)",
            "changes": {},
            "changes_summary": "—",
            "serialized_data": None,
            "additional_data": {
                "event": "login",
                "session_key": "7f3a9b2c1d8e4f5a6b7c8d9e0f1a2b3c",
                "device_name": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "ip_address": "192.168.1.42",
            },
            "remote_addr": "192.168.1.42",
            "remote_port": 54321,
            "cid": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
        },
        {
            "id": 2,
            "timestamp": ts(18),
            "action": 3,
            "action_label": "ACCESS",
            "actor": "juan.dela",
            "actor_display": "Juan Dela Cruz",
            "actor_email": "juan.dela@hydr8-hq.io",
            "content_type": "users.User",
            "object_pk": "b2c3d4e5-f6a7-8901-bcde-f23456789012",
            "object_repr": "Juan Dela Cruz (juan.dela)",
            "changes": {},
            "changes_summary": "—",
            "serialized_data": None,
            "additional_data": {
                "event": "login",
                "session_key": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
                "device_name": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) Mobile/15E148",
                "ip_address": "10.0.0.15",
            },
            "remote_addr": "10.0.0.15",
            "remote_port": 49832,
            "cid": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
        },
        {
            "id": 3,
            "timestamp": ts(45),
            "action": 3,
            "action_label": "ACCESS",
            "actor": "roberto.santos",
            "actor_display": "Roberto Santos",
            "actor_email": "roberto.santos@hydr8-hq.io",
            "content_type": "users.User",
            "object_pk": "c3d4e5f6-a7b8-9012-cdef-345678901234",
            "object_repr": "Roberto Santos (roberto.santos)",
            "changes": {},
            "changes_summary": "—",
            "serialized_data": None,
            "additional_data": {
                "event": "logout",
                "session_key": "e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
                "device_name": "Mozilla/5.0 (Android 13; Mobile; rv:121.0) Gecko/121.0",
                "ip_address": "203.0.113.55",
            },
            "remote_addr": "203.0.113.55",
            "remote_port": 51002,
            "cid": "550e8400-e29b-41d4-a716-446655440000",
        },
        # --- Customer mutations ---
        {
            "id": 4,
            "timestamp": ts(72),
            "action": 0,
            "action_label": "CREATE",
            "actor": "adrian.thorne",
            "actor_display": "Adrian Thorne",
            "actor_email": "adrian.thorne@hydr8-hq.io",
            "content_type": "customers.Customer",
            "object_pk": "42",
            "object_repr": "Greenfield Subdivision Association",
            "changes": {
                "name": [None, "Greenfield Subdivision Association"],
                "address": [None, "Block 12, Lot 5, Greenfield Ave, Calamba, Laguna"],
                "contact_number": [None, "+63 917 555 0142"],
                "debt_balance": [None, "0.00"],
            },
            "changes_summary": "4 field(s) changed",
            "serialized_data": {
                "model": "customers.customer",
                "pk": 42,
                "fields": {
                    "name": "Greenfield Subdivision Association",
                    "address": "Block 12, Lot 5, Greenfield Ave, Calamba, Laguna",
                    "contact_number": "+63 917 555 0142",
                    "debt_balance": "0.00",
                    "borrowed_round_8gal": 0,
                    "borrowed_slim_8gal": 0,
                    "borrowed_other": 0,
                },
            },
            "additional_data": {"source": "web"},
            "remote_addr": "192.168.1.42",
            "remote_port": 54321,
            "cid": "6ba7b811-9dad-11d1-80b4-00c04fd430c8",
        },
        {
            "id": 5,
            "timestamp": ts(95),
            "action": 1,
            "action_label": "UPDATE",
            "actor": "juan.dela",
            "actor_display": "Juan Dela Cruz",
            "actor_email": "juan.dela@hydr8-hq.io",
            "content_type": "customers.Customer",
            "object_pk": "17",
            "object_repr": "Maria's Sari-Sari Store",
            "changes": {
                "debt_balance": ["450.00", "890.00"],
                "borrowed_round_8gal": [5, 11],
                "last_credit_at": ["2026-08-09T10:30:00Z", "2026-08-11T08:15:00Z"],
            },
            "changes_summary": "3 field(s) changed",
            "serialized_data": {
                "model": "customers.customer",
                "pk": 17,
                "fields": {
                    "name": "Maria's Sari-Sari Store",
                    "debt_balance": "890.00",
                    "borrowed_round_8gal": 11,
                    "borrowed_slim_8gal": 3,
                    "borrowed_other": 0,
                    "last_credit_at": "2026-08-11T08:15:00Z",
                },
            },
            "additional_data": {"source": "web", "credit_line_id": 204},
            "remote_addr": "10.0.0.15",
            "remote_port": 49832,
            "cid": "6ba7b812-9dad-11d1-80b4-00c04fd430c8",
        },
        {
            "id": 6,
            "timestamp": ts(130),
            "action": 1,
            "action_label": "UPDATE",
            "actor": "adrian.thorne",
            "actor_display": "Adrian Thorne",
            "actor_email": "adrian.thorne@hydr8-hq.io",
            "content_type": "customers.Customer",
            "object_pk": "8",
            "object_repr": "St. Michael Parish",
            "changes": {
                "status": ["active", "blacklisted"],
                "notes": ["", "Multiple bounced checks. Flagged for collection review."],
            },
            "changes_summary": "2 field(s) changed",
            "serialized_data": {
                "model": "customers.customer",
                "pk": 8,
                "fields": {
                    "name": "St. Michael Parish",
                    "status": "blacklisted",
                    "debt_balance": "12400.00",
                    "notes": "Multiple bounced checks. Flagged for collection review.",
                },
            },
            "additional_data": {"source": "web"},
            "remote_addr": "192.168.1.42",
            "remote_port": 54321,
            "cid": "6ba7b813-9dad-11d1-80b4-00c04fd430c8",
        },
        # --- Remittance mutations ---
        {
            "id": 7,
            "timestamp": ts(180),
            "action": 0,
            "action_label": "CREATE",
            "actor": "juan.dela",
            "actor_display": "Juan Dela Cruz",
            "actor_email": "juan.dela@hydr8-hq.io",
            "content_type": "remittance.Remittance",
            "object_pk": "156",
            "object_repr": "Remittance 2026-08-11 (DRAFT)",
            "changes": {
                "date": [None, "2026-08-11"],
                "status": [None, "DRAFT"],
                "total_sales": [None, "4850.00"],
                "created_by": [None, "juan.dela"],
            },
            "changes_summary": "4 field(s) changed",
            "serialized_data": {
                "model": "remittance.remittance",
                "pk": 156,
                "fields": {
                    "date": "2026-08-11",
                    "status": "DRAFT",
                    "total_sales": "4850.00",
                    "net_profit": "3240.00",
                    "tithe_amount": "324.00",
                    "tithes_paid": False,
                },
            },
            "additional_data": {"source": "web"},
            "remote_addr": "10.0.0.15",
            "remote_port": 49832,
            "cid": "6ba7b814-9dad-11d1-80b4-00c04fd430c8",
        },
        {
            "id": 8,
            "timestamp": ts(210),
            "action": 1,
            "action_label": "UPDATE",
            "actor": "adrian.thorne",
            "actor_display": "Adrian Thorne",
            "actor_email": "adrian.thorne@hydr8-hq.io",
            "content_type": "remittance.Remittance",
            "object_pk": "155",
            "object_repr": "Remittance 2026-08-10 (FINALIZED)",
            "changes": {
                "status": ["DRAFT", "FINALIZED"],
                "finalized_by": [None, "adrian.thorne"],
                "finalized_at": [None, "2026-08-10T18:45:00Z"],
                "tithes_paid": [False, True],
            },
            "changes_summary": "4 field(s) changed",
            "serialized_data": {
                "model": "remittance.remittance",
                "pk": 155,
                "fields": {
                    "date": "2026-08-10",
                    "status": "FINALIZED",
                    "total_sales": "6200.00",
                    "net_profit": "4180.00",
                    "tithe_amount": "418.00",
                    "tithes_paid": True,
                    "finalized_at": "2026-08-10T18:45:00Z",
                },
            },
            "additional_data": {"source": "web"},
            "remote_addr": "192.168.1.42",
            "remote_port": 54321,
            "cid": "6ba7b815-9dad-11d1-80b4-00c04fd430c8",
        },
        # --- Product pricing mutation (PIN-gated) ---
        {
            "id": 9,
            "timestamp": ts(300),
            "action": 1,
            "action_label": "UPDATE",
            "actor": "adrian.thorne",
            "actor_display": "Adrian Thorne",
            "actor_email": "adrian.thorne@hydr8-hq.io",
            "content_type": "core.Product",
            "object_pk": "5",
            "object_repr": "Distilled Water 5gal",
            "changes": {
                "unit_price": ["38.00", "40.00"],
                "updated_at": ["2026-08-10T10:00:00Z", "2026-08-11T14:20:00Z"],
            },
            "changes_summary": "2 field(s) changed",
            "serialized_data": {
                "model": "core.product",
                "pk": 5,
                "fields": {
                    "name": "Distilled Water 5gal",
                    "unit_price": "40.00",
                    "is_default": False,
                    "is_active": True,
                },
            },
            "additional_data": {"source": "web", "pin_verified": True},
            "remote_addr": "192.168.1.42",
            "remote_port": 54321,
            "cid": "6ba7b816-9dad-11d1-80b4-00c04fd430c8",
        },
        # --- Settings mutation ---
        {
            "id": 10,
            "timestamp": ts(420),
            "action": 1,
            "action_label": "UPDATE",
            "actor": "adrian.thorne",
            "actor_display": "Adrian Thorne",
            "actor_email": "adrian.thorne@hydr8-hq.io",
            "content_type": "core.SystemConfig",
            "object_pk": "1",
            "object_repr": "SystemConfig: tithe_rate",
            "changes": {
                "value": ["8.00", "10.00"],
                "updated_at": ["2026-08-09T12:00:00Z", "2026-08-11T10:30:00Z"],
            },
            "changes_summary": "2 field(s) changed",
            "serialized_data": {
                "model": "core.systemconfig",
                "pk": 1,
                "fields": {"key": "tithe_rate", "value": "10.00"},
            },
            "additional_data": {"source": "web"},
            "remote_addr": "192.168.1.42",
            "remote_port": 54321,
            "cid": "6ba7b817-9dad-11d1-80b4-00c04fd430c8",
        },
        # --- User account mutation ---
        {
            "id": 11,
            "timestamp": ts(600),
            "action": 1,
            "action_label": "UPDATE",
            "actor": "adrian.thorne",
            "actor_display": "Adrian Thorne",
            "actor_email": "adrian.thorne@hydr8-hq.io",
            "content_type": "users.User",
            "object_pk": "b2c3d4e5-f6a7-8901-bcde-f23456789012",
            "object_repr": "Juan Dela Cruz (juan.dela)",
            "changes": {
                "role": ["Driver", "Senior Driver"],
                "force_password_change": [True, False],
                "updated_at": ["2026-08-10T08:00:00Z", "2026-08-11T06:45:00Z"],
            },
            "changes_summary": "3 field(s) changed",
            "serialized_data": {
                "model": "users.user",
                "pk": "b2c3d4e5-f6a7-8901-bcde-f23456789012",
                "fields": {
                    "username": "juan.dela",
                    "first_name": "Juan",
                    "last_name": "Dela Cruz",
                    "role": "Senior Driver",
                    "force_password_change": False,
                    "is_active": True,
                },
            },
            "additional_data": {"source": "web"},
            "remote_addr": "192.168.1.42",
            "remote_port": 54321,
            "cid": "6ba7b818-9dad-11d1-80b4-00c04fd430c8",
        },
        # --- Delete event ---
        {
            "id": 12,
            "timestamp": ts(850),
            "action": 2,
            "action_label": "DELETE",
            "actor": "adrian.thorne",
            "actor_display": "Adrian Thorne",
            "actor_email": "adrian.thorne@hydr8-hq.io",
            "content_type": "customers.Customer",
            "object_pk": "3",
            "object_repr": "Old Depot Refilling (DELETED)",
            "changes": {
                "name": ["Old Depot Refilling", None],
                "debt_balance": ["0.00", None],
                "deleted_at": [None, "2026-08-10T22:10:00Z"],
            },
            "changes_summary": "3 field(s) changed",
            "serialized_data": {
                "model": "customers.customer",
                "pk": 3,
                "fields": {
                    "name": "Old Depot Refilling",
                    "debt_balance": "0.00",
                    "deleted_at": "2026-08-10T22:10:00Z",
                },
            },
            "additional_data": {"source": "web", "soft_delete": True},
            "remote_addr": "192.168.1.42",
            "remote_port": 54321,
            "cid": "6ba7b819-9dad-11d1-80b4-00c04fd430c8",
        },
        # --- Failed login attempt (lockout) ---
        {
            "id": 13,
            "timestamp": ts(920),
            "action": 3,
            "action_label": "ACCESS",
            "actor": None,
            "actor_display": "System",
            "actor_email": None,
            "content_type": "users.User",
            "object_pk": "unknown",
            "object_repr": "Failed login: username='admin' (5 attempts)",
            "changes": {},
            "changes_summary": "—",
            "serialized_data": None,
            "additional_data": {
                "event": "login_failed",
                "username": "admin",
                "failed_attempts": 5,
                "locked_until": "2026-08-10T20:25:00Z",
                "ip_address": "198.51.100.23",
            },
            "remote_addr": "198.51.100.23",
            "remote_port": 41200,
            "cid": "6ba7b81a-9dad-11d1-80b4-00c04fd430c8",
        },
        # --- Password change ---
        {
            "id": 14,
            "timestamp": ts(1100),
            "action": 1,
            "action_label": "UPDATE",
            "actor": "roberto.santos",
            "actor_display": "Roberto Santos",
            "actor_email": "roberto.santos@hydr8-hq.io",
            "content_type": "users.User",
            "object_pk": "c3d4e5f6-a7b8-9012-cdef-345678901234",
            "object_repr": "Roberto Santos (roberto.santos)",
            "changes": {
                "password": ["[hashed]", "[hashed]"],
                "password_last_updated_at": ["2026-05-13T10:00:00Z", "2026-08-10T15:30:00Z"],
                "password_expires_at": ["2026-08-11T10:00:00Z", "2026-11-08T15:30:00Z"],
            },
            "changes_summary": "3 field(s) changed",
            "serialized_data": None,
            "additional_data": {
                "source": "web",
                "event": "password_change",
                "sessions_invalidated": 2,
            },
            "remote_addr": "203.0.113.55",
            "remote_port": 51002,
            "cid": "6ba7b81b-9dad-11d1-80b4-00c04fd430c8",
        },
        # --- Commission rate matrix update ---
        {
            "id": 15,
            "timestamp": ts(1300),
            "action": 1,
            "action_label": "UPDATE",
            "actor": "adrian.thorne",
            "actor_display": "Adrian Thorne",
            "actor_email": "adrian.thorne@hydr8-hq.io",
            "content_type": "users.DriverCommission",
            "object_pk": "78",
            "object_repr": "Juan Dela Cruz - 5gal Alkaline Round",
            "changes": {
                "rate_per_unit": ["3.50", "4.00"],
                "updated_at": ["2026-08-09T14:00:00Z", "2026-08-10T11:20:00Z"],
            },
            "changes_summary": "2 field(s) changed",
            "serialized_data": {
                "model": "users.drivercommission",
                "pk": 78,
                "fields": {
                    "driver": "Juan Dela Cruz",
                    "product": "5gal Alkaline Round",
                    "rate_per_unit": "4.00",
                },
            },
            "additional_data": {"source": "web"},
            "remote_addr": "192.168.1.42",
            "remote_port": 54321,
            "cid": "6ba7b81c-9dad-11d1-80b4-00c04fd430c8",
        },
        # --- System scheduler action ---
        {
            "id": 16,
            "timestamp": ts(1440),
            "action": 2,
            "action_label": "DELETE",
            "actor": None,
            "actor_display": "system-scheduler",
            "actor_email": "scheduler@hydr8-hq.io",
            "content_type": "auditlog.LogEntry",
            "object_pk": "various",
            "object_repr": "Retention shred: 47 expired LogEntry records",
            "changes": {},
            "changes_summary": "—",
            "serialized_data": None,
            "additional_data": {
                "source": "system",
                "event": "retention_shred",
                "model_label": "auditlog.LogEntry",
                "deleted_count": 47,
                "cutoff": "2026-05-11T00:00:00Z",
                "retention_months": 3,
            },
            "remote_addr": None,
            "remote_port": None,
            "cid": "6ba7b81d-9dad-11d1-80b4-00c04fd430c8",
        },
    ]


def _build_context() -> dict:
    """Builds the template context for the audit log list page."""
    logs = _mock_audit_logs()

    # Enrich each entry with badge styling
    for entry in logs:
        entry["badge_class"] = _ACTION_BADGE_CLASSES.get(
            entry["action"], "bg-surface-container text-on-surface-variant"
        )

    # Action filter options
    action_filters = [
        {"value": "", "label": "All Actions", "count": len(logs), "active": True},
        {"value": "0", "label": "Create", "count": sum(1 for e in logs if e["action"] == 0), "active": False},
        {"value": "1", "label": "Update", "count": sum(1 for e in logs if e["action"] == 1), "active": False},
        {"value": "2", "label": "Delete", "count": sum(1 for e in logs if e["action"] == 2), "active": False},
        {"value": "3", "label": "Access", "count": sum(1 for e in logs if e["action"] == 3), "active": False},
    ]

    # Summary stats
    stats = [
        {
            "label": "Total Entries",
            "value": str(len(logs)),
            "icon": "history",
            "accent": "text-primary",
        },
        {
            "label": "Mutations",
            "value": str(sum(1 for e in logs if e["action"] in (0, 1, 2))),
            "icon": "edit_note",
            "accent": "text-tertiary",
        },
        {
            "label": "Access Events",
            "value": str(sum(1 for e in logs if e["action"] == 3)),
            "icon": "login",
            "accent": "text-[#D97706]",
        },
        {
            "label": "Active Actors",
            "value": str(len({e["actor"] for e in logs if e["actor"]})),
            "icon": "group",
            "accent": "text-secondary",
        },
    ]

    pagination = {
        "showing_from": 1,
        "showing_to": len(logs),
        "total_display": str(len(logs)),
        "current_page": 1,
        "total_pages": 1,
    }

    # JSON-serializable projection of logs for Alpine.js client-side filtering.
    # Only the fields needed for display + filtering are included.
    logs_json = json.dumps([
        {
            "id": e["id"],
            "timestamp": e["timestamp"],
            "action": e["action"],
            "action_label": e["action_label"],
            "badge_class": e["badge_class"],
            "actor_display": e["actor_display"],
            "actor_email": e.get("actor_email"),
            "is_system": e["actor_display"] in ("System", "system-scheduler"),
            "initials": e["actor_display"][:2].upper(),
            "content_type": e["content_type"],
            "object_repr": e["object_repr"],
            "changes_summary": e["changes_summary"],
            "remote_addr": e.get("remote_addr"),
            "cid": e.get("cid"),
        }
        for e in logs
    ])

    return {
        "today_date": datetime.now().strftime("%A, %b %d, %Y"),
        "logs": logs,
        "action_filters": action_filters,
        "stats": stats,
        "pagination": pagination,
        "logs_json": logs_json,
    }


@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='120/m', method='GET', block=True)
def audit_log_view(request):
    """
    Renders the Audit Log page — a table of all system mutations and
    access events, mirroring the django-auditlog LogEntry schema.

    Currently uses mock data (``_build_context``) to prototype the UI.
    When backend services are ready, swap the mock call for a real
    selector querying ``auditlog.models.LogEntry``.
    """
    context = _build_context()
    return render(request, "audit/audit_log.html", context)


@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='60/m', method='GET', block=True)
def audit_log_detail_view(request, entry_id: int):
    """
    HTMX endpoint — returns the detail modal partial for a single
    audit log entry, showing the full field-level Before/After diff
    and serialized data snapshot.

    Mirrors the Monito HR unofficial ChangesDiffModal pattern: the
    table row triggers an HTMX GET that swaps the modal partial into
    #modal-root.
    """
    logs = _mock_audit_logs()
    entry = next((e for e in logs if e["id"] == entry_id), None)

    if entry is None:
        return HttpResponse("Audit log entry not found.", status=404)

    entry["badge_class"] = _ACTION_BADGE_CLASSES.get(
        entry["action"], "bg-surface-container text-on-surface-variant"
    )

    # Format changes for the diff table — convert {field: [old, new]} to list
    changes_list = []
    if entry["changes"]:
        for field, values in entry["changes"].items():
            changes_list.append({
                "field": field,
                "old": values[0] if values[0] is not None else "—",
                "new": values[1] if values[1] is not None else "—",
                "is_new_field": values[0] is None,
                "is_deleted_field": values[1] is None,
            })
    entry["changes_list"] = changes_list

    # Pretty-print serialized data and additional_data for the collapsible sections
    if entry["serialized_data"]:
        entry["serialized_data_pretty"] = json.dumps(entry["serialized_data"], indent=2)
    if entry["additional_data"]:
        entry["additional_data_pretty"] = json.dumps(entry["additional_data"], indent=2)

    return render(request, "audit/partials/detail_modal.html", {"entry": entry})
