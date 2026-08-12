"""Tests for the audit log selectors."""
from django.test import TestCase

from apps.audit.selectors import list_log_entries, get_log_entry
from apps.users.models import User


class ListLogEntriesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )

    def test_returns_paginated_data(self):
        data = list_log_entries(user=self.user, page=1)
        self.assertIn("page_obj", data)
        self.assertIn("paginator", data)
        self.assertIn("total", data)
        self.assertIn("action_counts", data)
        self.assertIn("active_actors", data)

    def test_empty_log_returns_zero_counts(self):
        # Creating a user triggers auditlog's CREATE signal (User is registered),
        # so there is 1 entry (the user creation itself). We verify the structure
        # and that no ACCESS events exist yet.
        data = list_log_entries(user=self.user, page=1)
        self.assertGreaterEqual(data["total"], 1)
        self.assertEqual(data["action_counts"].get(3, 0), 0)  # no ACCESS events

    def test_invalid_page_falls_back_to_last_page(self):
        data = list_log_entries(user=self.user, page=999)
        # Django's get_page clamps to the last valid page
        self.assertLessEqual(data["page_obj"].number, 1)


class GetLogEntryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )

    def test_nonexistent_entry_returns_none(self):
        result = get_log_entry(entry_id=99999, user=self.user)
        self.assertIsNone(result)
