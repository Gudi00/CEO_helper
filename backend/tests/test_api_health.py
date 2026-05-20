import pytest


@pytest.mark.asyncio
async def test_health_does_not_require_token(client):
    del client.headers["X-Backend-Token"]
    r = await client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


@pytest.mark.asyncio
async def test_session_requires_token(client):
    del client.headers["X-Backend-Token"]
    r = await client.post("/api/session/start", json={"mode": "assist", "cmid": "1"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_session_start_then_get(client):
    r = await client.post(
        "/api/session/start",
        json={"mode": "assist", "cmid": "305095", "access_strategy": "extension_native"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    sid = body["session_id"]
    assert body["ws_url"].endswith(sid)

    r2 = await client.get(f"/api/session/{sid}")
    assert r2.status_code == 200
    assert r2.json()["status"] == "running"


@pytest.mark.asyncio
async def test_session_stop(client):
    sid = (
        await client.post(
            "/api/session/start", json={"mode": "assist", "cmid": "1"}
        )
    ).json()["session_id"]
    r = await client.post(f"/api/session/{sid}/stop")
    assert r.status_code == 204
    state = (await client.get(f"/api/session/{sid}")).json()
    assert state["status"] == "aborted"
