from django.test import Client


def test_health_endpoint_is_documented(client: Client) -> None:
    health_response = client.get("/api/health")

    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}

    schema_response = client.get("/api/openapi.json")
    assert schema_response.status_code == 200
    assert "/api/health" in schema_response.json()["paths"]

    docs_response = client.get("/api/docs")
    assert docs_response.status_code == 200
    assert b"swagger" in docs_response.content.lower()
