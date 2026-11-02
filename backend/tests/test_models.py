import pytest


def test_llm_model_routes_require_admin(client, headers):
    assert client.get("/api/admin/models/status").status_code == 401
    assert client.get("/api/admin/models/status", headers=headers()).status_code == 403
    assert client.post("/api/admin/models/switch", json={"provider": "local"}).status_code == 401
    assert client.post(
        "/api/admin/models/switch",
        headers=headers(),
        json={"provider": "local"},
    ).status_code == 403
    assert client.patch("/api/admin/models/remote", json={
        "base_url": "https://example.invalid/v1",
        "model": "remote-model",
        "api_key": "test-key",
    }).status_code == 401
    assert client.patch("/api/admin/models/remote", headers=headers(), json={
        "base_url": "https://example.invalid/v1",
        "model": "remote-model",
        "api_key": "test-key",
    }).status_code == 403


def test_local_and_remote_answer_model_switch(client, headers, settings):
    auth = headers("admin")
    initial = client.get("/api/admin/models/status", headers=auth)
    assert initial.status_code == 200
    assert initial.json()["active_provider"] == "local"
    local = next(profile for profile in initial.json()["profiles"] if profile["id"] == "local")
    remote = next(profile for profile in initial.json()["profiles"] if profile["id"] == "remote")
    assert local["configured"] is True
    assert remote["configured"] is False

    unavailable = client.post(
        "/api/admin/models/switch",
        headers=auth,
        json={"provider": "remote"},
    )
    assert unavailable.status_code == 409

    configured = client.patch(
        "/api/admin/models/remote",
        headers=auth,
        json={
            "base_url": "https://example.invalid/v1",
            "model": "remote-model",
            "api_key": "test-key",
        },
    )
    assert configured.status_code == 200
    remote = next(profile for profile in configured.json()["profiles"] if profile["id"] == "remote")
    assert remote["configured"] is True
    assert remote["base_url"] == "https://example.invalid/v1"
    assert remote["model"] == "remote-model"
    assert "test-key" not in configured.text
    stored = (settings.model_cache_dir / "remote-llm.json").read_text(encoding="utf-8")
    assert "test-key" not in stored

    switched = client.post(
        "/api/admin/models/switch",
        headers=auth,
        json={"provider": "remote"},
    )
    assert switched.status_code == 200
    assert switched.json()["active_provider"] == "remote"

    restored = client.post(
        "/api/admin/models/switch",
        headers=auth,
        json={"provider": "local"},
    )
    assert restored.status_code == 200
    assert restored.json()["active_provider"] == "local"


@pytest.mark.parametrize("provider", ["unknown"])
def test_llm_model_rejects_unknown_provider(client, headers, provider):
    response = client.post(
        "/api/admin/models/switch",
        headers=headers("admin"),
        json={"provider": provider},
    )
    assert response.status_code == 422
