from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_apitoken"),
    ]

    operations = [
        migrations.AddField(
            model_name="run",
            name="failure_detail",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="run",
            name="failure_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("setup_failed", "Setup failed"),
                    ("sandbox_died", "Sandbox died"),
                    ("agent_error", "Agent error"),
                    ("agent_reported_failed", "Agent reported failed"),
                    ("agent_reported_blocked", "Agent reported blocked"),
                    ("no_result", "No result"),
                    ("canceled", "Canceled"),
                ],
                max_length=40,
            ),
        ),
        migrations.AddConstraint(
            model_name="org",
            constraint=models.CheckConstraint(
                condition=models.Q(("concurrency_cap__gte", 1)),
                name="org_concurrency_cap_at_least_one",
            ),
        ),
    ]
