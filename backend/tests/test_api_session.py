from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_get_unknown_session_returns_404(client):
    r = await client.get(f"/api/session/{uuid4()}")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_stop_unknown_session_returns_404(client):
    r = await client.post(f"/api/session/{uuid4()}/stop")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_double_stop_keeps_status_aborted(client):
    sid = (
        await client.post(
            "/api/session/start", json={"mode": "assist", "cmid": "1"}
        )
    ).json()["session_id"]

    await client.post(f"/api/session/{sid}/stop")
    await client.post(f"/api/session/{sid}/stop")

    state = (await client.get(f"/api/session/{sid}")).json()
    assert state["status"] == "aborted"


@pytest.mark.asyncio
async def test_session_start_validation_error_on_missing_fields(client):
    r = await client.post("/api/session/start", json={"mode": "assist"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_session_start_rejects_unknown_mode(client):
    r = await client.post(
        "/api/session/start", json={"mode": "explode", "cmid": "1"}
    )
    assert r.status_code == 422
