# Generated for the collect-submit flow — counter collections (customer
# payments recorded at the counter via the Collect modal) are not tied to
# a rider's daily remittance, so CreditPayment.remittance must be nullable.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0009_borrowed_container_and_creditline_care_of'),
        ('remittance', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='creditpayment',
            name='remittance',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='credit_payments',
                to='remittance.remittance',
            ),
        ),
    ]
