from __future__ import annotations

import pytest

from src import pairing


@pytest.fixture(autouse=True)
def _reset_pairing():
    pairing.reset()
    yield
    pairing.reset()


def test_code_is_single_use():
    code = pairing.issue_code()
    assert pairing.redeem(code) is True
    assert pairing.redeem(code) is False


def test_code_expires(monkeypatch):
    code = pairing.issue_code()
    now = pairing.time.monotonic()
    monkeypatch.setattr(pairing.time, "monotonic", lambda: now + pairing.CODE_TTL_S + 1)
    assert pairing.redeem(code) is False


def test_code_is_dropped_after_too_many_wrong_guesses():
    code = pairing.issue_code()
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(pairing.MAX_FAILURES):
        assert pairing.redeem(wrong) is False
    assert pairing.redeem(code) is False


@pytest.mark.asyncio
async def test_pair_endpoint_trades_code_for_token(client):
    r = await client.post("/api/pair/new")
    assert r.status_code == 200
    code = r.json()["code"]

    del client.headers["X-Backend-Token"]
    r = await client.post("/api/pair", json={"code": code})
    assert r.status_code == 200
    assert r.json()["token"] == "test-token"

    r = await client.post("/api/pair", json={"code": code})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "PAIRING_FAILED"


@pytest.mark.asyncio
async def test_new_code_requires_token(client):
    del client.headers["X-Backend-Token"]
    r = await client.post("/api/pair/new")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_unknown_host_header_is_rejected(client):
    r = await client.get("/api/health", headers={"Host": "evil.example"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_after_pairing_other_extensions_are_refused(client):
    mine = {"Origin": "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
    other = {"Origin": "chrome-extension://bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}

    # Before any pairing a hand-pasted token works from any extension.
    assert (await client.get("/api/models", headers=other)).status_code == 200

    code = (await client.post("/api/pair/new")).json()["code"]
    assert (await client.post("/api/pair", json={"code": code}, headers=mine)).status_code == 200

    assert (await client.get("/api/models", headers=mine)).status_code == 200
    refused = await client.get("/api/models", headers=other)
    assert refused.status_code == 403
    assert refused.json()["detail"]["code"] == "ORIGIN_NOT_PAIRED"
    # Requests without an Origin (CLI, curl) are still governed by the token alone.
    assert (await client.get("/api/models")).status_code == 200
