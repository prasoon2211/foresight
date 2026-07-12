from django.test import Client


def test_health_endpoint_is_documented(client: Client) -> None:
    health_response = client.get("/api/health")

    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}

    schema_response = client.get("/api/openapi.json")
    assert schema_response.status_code == 200
    schema = schema_response.json()
    assert "/api/health" in schema["paths"]

    docs_response = client.get("/api/docs")
    assert docs_response.status_code == 200
    assert b"swagger" in docs_response.content.lower()


def test_openapi_documents_session_cookie_and_bearer_token(client: Client) -> None:
    schema = client.get("/api/openapi.json").json()

    schemes = schema["components"]["securitySchemes"]
    assert {definition["type"] for definition in schemes.values()} == {
        "apiKey",
        "http",
    }
    assert any(
        definition.get("in") == "cookie" and definition.get("name") == "sessionid"
        for definition in schemes.values()
    )
    assert any(definition.get("scheme") == "bearer" for definition in schemes.values())
    signal_security = schema["paths"]["/api/orgs/{org_id}/signals"]["post"]["security"]
    assert len(signal_security) == 2
