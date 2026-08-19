"""Tests for audit log tenant scoping and search.

Covers:
  - _tenant_filter: company isolation for regular users vs superusers
  - list_log_entries: search query filtering
  - get_log_entry: tenant isolation
  - build_logs_json: JSON serialization structure
"""
import json

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from apps.core.selectors_audit import (
    _tenant_filter,
    get_log_entry,
    list_log_entries,
)
from apps.core.presentation_audit import build_logs_json, enrich_entry
from apps.core.models import Company
from apps.users.models import User
from auditlog.models import LogEntry


def _make_log_entry(actor, object_repr="Test Object", action=LogEntry.Action.UPDATE):
    """Creates a LogEntry for the given actor."""
    return LogEntry.objects.create(
        content_type=ContentType.objects.get_for_model(User),
        action=action,
        actor=actor,
        object_repr=object_repr,
        object_pk=str(actor.pk) if actor else "1",
        changes={"field": ["old", "new"]},
    )


class TenantFilterTests(TestCase):
    """Tests for the _tenant_filter helper."""

    def setUp(self):
        self.company_a = Company.objects.create(name="Company A")
        self.company_b = Company.objects.create(name="Company B")
        self.user_a = User.objects.create_user(
            username="user_a", password="pass123", company=self.company_a
        )
        self.user_b = User.objects.create_user(
            username="user_b", password="pass123", company=self.company_b
        )
        self.superuser = User.objects.create_superuser(
            username="super", password="pass123"
        )
        # Create explicit log entries for each user
        self.entry_a = _make_log_entry(self.user_a, "User A Object")
        self.entry_b = _make_log_entry(self.user_b, "User B Object")

    def test_superuser_sees_all_entries(self):
        """A superuser (company_id is None) sees all log entries."""
        qs = LogEntry.objects.all()
        filtered = _tenant_filter(qs, self.superuser)
        self.assertGreaterEqual(filtered.count(), 2)

    def test_regular_user_filtered_by_company(self):
        """A regular user only sees entries from actors in their company."""
        qs = LogEntry.objects.all()
        filtered = _tenant_filter(qs, self.user_a)
        # user_a should see entry_a but not entry_b
        pks = list(filtered.values_list("pk", flat=True))
        self.assertIn(self.entry_a.pk, pks)
        self.assertNotIn(self.entry_b.pk, pks)

    def test_user_b_filtered_to_company_b(self):
        """User B only sees entries from actors in company B."""
        qs = LogEntry.objects.all()
        filtered = _tenant_filter(qs, self.user_b)
        pks = list(filtered.values_list("pk", flat=True))
        self.assertIn(self.entry_b.pk, pks)
        self.assertNotIn(self.entry_a.pk, pks)


class ListLogEntriesSearchTests(TestCase):
    """Tests for list_log_entries search functionality."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="searchuser",
            password="pass123",
            first_name="Search",
            last_name="Tester",
        )
        # Create an explicit log entry with the user as actor
        self.entry = _make_log_entry(self.user, "Search User Object")

    def test_search_by_username(self):
        """Searching by username filters the log entries."""
        data = list_log_entries(user=self.user, query="searchuser")
        self.assertGreaterEqual(data["total"], 1)

    def test_search_by_first_name(self):
        """Searching by first name filters the log entries."""
        data = list_log_entries(user=self.user, query="Search")
        self.assertGreaterEqual(data["total"], 1)

    def test_search_by_object_repr(self):
        """Searching by object_repr filters the log entries."""
        data = list_log_entries(user=self.user, query="Search User Object")
        self.assertGreaterEqual(data["total"], 1)

    def test_empty_query_returns_all(self):
        """An empty query returns all entries."""
        data_all = list_log_entries(user=self.user, query="")
        data_none = list_log_entries(user=self.user)
        self.assertEqual(data_all["total"], data_none["total"])

    def test_no_results_for_nonexistent_query(self):
        """A query that matches nothing returns zero results."""
        data = list_log_entries(user=self.user, query="zzz_nonexistent_zzz")
        self.assertEqual(data["total"], 0)

    def test_whitespace_query_trimmed(self):
        """A whitespace-only query is trimmed and returns all entries."""
        data = list_log_entries(user=self.user, query="   ")
        data_all = list_log_entries(user=self.user, query="")
        self.assertEqual(data["total"], data_all["total"])


class GetLogEntryTenantTests(TestCase):
    """Tests for get_log_entry tenant isolation."""

    def setUp(self):
        self.company_a = Company.objects.create(name="Company A")
        self.company_b = Company.objects.create(name="Company B")
        self.user_a = User.objects.create_user(
            username="user_a", password="pass123", company=self.company_a
        )
        self.user_b = User.objects.create_user(
            username="user_b", password="pass123", company=self.company_b
        )
        self.superuser = User.objects.create_superuser(
            username="super", password="pass123"
        )
        self.entry_a = _make_log_entry(self.user_a, "User A Object")
        self.entry_b = _make_log_entry(self.user_b, "User B Object")

    def test_user_can_retrieve_own_company_entry(self):
        """A user can retrieve a log entry from their own company."""
        result = get_log_entry(entry_id=self.entry_a.pk, user=self.user_a)
        self.assertIsNotNone(result)
        self.assertEqual(result.pk, self.entry_a.pk)

    def test_user_cannot_see_other_company_entry(self):
        """A user cannot retrieve a log entry from another company."""
        result = get_log_entry(entry_id=self.entry_b.pk, user=self.user_a)
        self.assertIsNone(result)

    def test_superuser_can_see_any_entry(self):
        """A superuser can retrieve any company's log entry."""
        result = get_log_entry(entry_id=self.entry_a.pk, user=self.superuser)
        self.assertIsNotNone(result)

    def test_retrieved_entry_can_be_enriched(self):
        """The retrieved entry can be enriched by presentation_audit.enrich_entry."""
        result = get_log_entry(entry_id=self.entry_a.pk, user=self.user_a)
        self.assertIsNotNone(result)
        enrich_entry(result)
        self.assertTrue(hasattr(result, "action_label"))
        self.assertTrue(hasattr(result, "badge_class"))
        self.assertTrue(hasattr(result, "actor_display"))
        self.assertTrue(hasattr(result, "content_type_str"))


class BuildLogsJsonTests(TestCase):
    """Tests for build_logs_json serialization."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="jsonuser", password="pass123"
        )
        self.entry = _make_log_entry(self.user, "JSON Test Object")

    def test_returns_valid_json_array(self):
        """build_logs_json returns a parseable JSON array."""
        data = list_log_entries(user=self.user, page=1)
        for e in data["page_obj"].object_list:
            enrich_entry(e)
        json_str = build_logs_json(data["page_obj"].object_list)
        parsed = json.loads(json_str)
        self.assertIsInstance(parsed, list)

    def test_empty_entries_returns_empty_array(self):
        """An empty entries list produces an empty JSON array."""
        json_str = build_logs_json([])
        self.assertEqual(json.loads(json_str), [])

    def test_entry_contains_required_fields(self):
        """Each serialized entry contains all required fields."""
        data = list_log_entries(user=self.user, page=1)
        if not data["page_obj"].object_list:
            self.skipTest("No log entries to serialize")
        for e in data["page_obj"].object_list:
            enrich_entry(e)
        json_str = build_logs_json(data["page_obj"].object_list)
        parsed = json.loads(json_str)
        required_fields = {
            "id", "timestamp", "action", "action_label", "badge_class",
            "actor_display", "actor_email", "is_system", "initials",
            "content_type", "object_repr", "changes_summary",
            "remote_addr", "cid",
        }
        self.assertTrue(required_fields.issubset(set(parsed[0].keys())))
