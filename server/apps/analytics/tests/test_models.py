from decimal import Decimal
from django.test import SimpleTestCase
from apps.analytics.models import DailySnapshot
from apps.tests.fakes import GenericFakeRepository


class DailySnapshotModelTests(SimpleTestCase):
    def test_daily_snapshot_str(self):
        """Test DailySnapshot string representation."""
        snapshot = DailySnapshot(snapshot_date="2026-08-02")
        self.assertEqual(str(snapshot), "Snapshot for 2026-08-02")

    def test_daily_snapshot_defaults(self):
        """Test DailySnapshot numerical field default values."""
        snapshot = DailySnapshot(snapshot_date="2026-08-02")
        self.assertEqual(snapshot.total_sales, Decimal("0.00") if isinstance(snapshot.total_sales, Decimal) else 0.00)
        self.assertEqual(snapshot.net_profit, Decimal("0.00") if isinstance(snapshot.net_profit, Decimal) else 0.00)
        self.assertEqual(snapshot.total_borrowed_items, 0)

    def test_fake_analytics_repository(self):
        """Test analytics snapshot tracking using fake repository."""
        repo = GenericFakeRepository()
        snap_data = {
            'snapshot_date': '2026-08-02',
            'total_sales': 5000.00,
            'net_profit': 3500.00,
            'total_borrowed_items': 12
        }
        repo.add('2026-08-02', snap_data)

        retrieved = repo.get('2026-08-02')
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved['total_sales'], 5000.00)
        self.assertEqual(retrieved['total_borrowed_items'], 12)
