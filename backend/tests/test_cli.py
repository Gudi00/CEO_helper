from __future__ import annotations

import httpx

from src import cli


def test_doctor_reports_stopped_server_and_missing_sources(monkeypatch, capsys):
    def refuse(*_a, **_kw):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(cli.httpx, "get", refuse)
    monkeypatch.setattr(cli.socket.socket, "connect_ex", lambda *_a: 1)

    code = cli.main(["doctor"])

    out = capsys.readouterr().out
    assert code == 1
    assert "lms-tool run" in out
    assert "Не настроен ни один источник" in out


def test_pair_explains_when_server_is_down(monkeypatch, capsys):
    def refuse(*_a, **_kw):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(cli.httpx, "post", refuse)

    assert cli.main(["pair"]) == 1
    assert "lms-tool run" in capsys.readouterr().out


def test_pair_prints_code(monkeypatch, capsys):
    request = httpx.Request("POST", "http://127.0.0.1:8765/api/pair/new")
    monkeypatch.setattr(
        cli.httpx,
        "post",
        lambda *_a, **_kw: httpx.Response(
            200, json={"code": "123456", "ttl_s": 120}, request=request
        ),
    )

    assert cli.main(["pair"]) == 0
    assert "123456" in capsys.readouterr().out
