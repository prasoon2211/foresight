from __future__ import annotations

from collections.abc import Iterator

import pytest
from django.db import connection, models
from encrypted_fields.fields import EncryptedTextField


class EncryptedValue(models.Model):
    value = EncryptedTextField()
    objects: models.Manager[EncryptedValue] = models.Manager()

    class Meta:
        app_label = "core"
        db_table = "test_encrypted_value"


@pytest.fixture
def encrypted_value_table(transactional_db: None) -> Iterator[None]:
    with connection.schema_editor() as schema_editor:
        schema_editor.create_model(EncryptedValue)
    yield
    with connection.schema_editor() as schema_editor:
        schema_editor.delete_model(EncryptedValue)


@pytest.mark.django_db(transaction=True)
def test_encrypted_field_round_trips_without_storing_plaintext(
    encrypted_value_table: None,
) -> None:
    secret = "credential-only-the-owner-knows"
    encrypted_value = EncryptedValue.objects.create(value=secret)

    assert EncryptedValue.objects.get(pk=encrypted_value.pk).value == secret

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT value FROM test_encrypted_value WHERE id = %s",
            [encrypted_value.pk],
        )
        stored_value = cursor.fetchone()[0]

    assert secret not in stored_value
