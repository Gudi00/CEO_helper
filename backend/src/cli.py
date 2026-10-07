"""`lms-tool` command: run the backend, pair the extension, self-diagnose."""

from __future__ import annotations

import argparse
import socket
import sys
from collections.abc import Callable
from pathlib import Path

import httpx

from src import __version__, autostart
from src.config import Settings, get_settings, user_config_dir

ENV_TEMPLATE = """\
# Настройки СЭО helper. Достаточно заполнить ЛЮБОЙ один источник ответов.
# После изменений перезапустите сервер. Проверка: lms-tool doctor

# --- 1. Google Gemini (ключ: https://aistudio.google.com/apikey) ---
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.0-flash

# --- 2. Любой OpenAI-совместимый API ---
#   OpenRouter: https://openrouter.ai/api/v1
#   DeepSeek:   https://api.deepseek.com/v1
#   Groq:       https://api.groq.com/openai/v1
#   LM Studio:  http://localhost:1234/v1
OPENAI_BASE_URL=
OPENAI_API_KEY=
OPENAI_MODEL=
# Более сильная модель для режима «Точная» (необязательно)
OPENAI_MODEL_ACCURATE=

# --- 3. Локальная модель через Ollama (https://ollama.com) ---
OLLAMA_ENABLED=false
OLLAMA_MODEL=gemma3:4b
OLLAMA_MODEL_ACCURATE=deepseek-r1:7b
"""


def _base_url(settings: Settings) -> str:
    host = "127.0.0.1" if settings.backend_host == "0.0.0.0" else settings.backend_host  # noqa: S104
    return f"http://{host}:{settings.backend_port}"


def cmd_run(_args: argparse.Namespace) -> int:
    import uvicorn

    # Imported as an object (not "src.main:app") so a frozen build finds it.
    from src.main import app

    settings = get_settings()
    uvicorn.run(
        app,
        host=settings.backend_host,
        port=settings.backend_port,
        log_level=settings.log_level.lower(),
    )
    return 0


def cmd_pair(_args: argparse.Namespace) -> int:
    settings = get_settings()
    try:
        r = httpx.post(
            f"{_base_url(settings)}/api/pair/new",
            headers={"X-Backend-Token": settings.ensure_token()},
            timeout=5,
        )
        r.raise_for_status()
    except httpx.HTTPError:
        print("Сервер не отвечает. Сначала запустите его: lms-tool run")
        return 1
    data = r.json()
    print(f"Код сопряжения: {data['code']} (действует {data['ttl_s'] // 60} мин)")
    print("Введите его в окне расширения: «Связать с сервером».")
    return 0


def _check_server(settings: Settings) -> tuple[bool, str]:
    try:
        r = httpx.get(f"{_base_url(settings)}/api/health", timeout=3)
        r.raise_for_status()
    except httpx.HTTPError:
        with socket.socket() as s:
            s.settimeout(1)
            busy = s.connect_ex(("127.0.0.1", settings.backend_port)) == 0
        if busy:
            return False, (
                f"порт {settings.backend_port} занят другой программой — "
                "задайте BACKEND_PORT в .env"
            )
        return False, "не запущен — выполните: lms-tool run"
    return True, f"работает, версия {r.json().get('version', '?')}"


def _check_gemini(settings: Settings) -> tuple[bool, str]:
    if settings.gemini_api_key:
        return True, f"ключ задан, модель {settings.gemini_model}"
    return False, "ключ не задан — добавьте GEMINI_API_KEY в .env (необязательно)"


def _check_openai(settings: Settings) -> tuple[bool, str]:
    if settings.openai_enabled:
        return True, f"{settings.openai_base_url}, модель {settings.openai_model}"
    return False, "не настроен — задайте OPENAI_BASE_URL и OPENAI_MODEL (необязательно)"


def _check_ollama(settings: Settings) -> tuple[bool, str]:
    if not settings.ollama_enabled:
        return False, "выключена — OLLAMA_ENABLED=true в .env (необязательно)"
    try:
        r = httpx.get(f"{settings.ollama_host}/api/tags", timeout=3)
        r.raise_for_status()
    except httpx.HTTPError:
        return False, f"не отвечает по адресу {settings.ollama_host} — запустите: ollama serve"
    installed = {m.get("name", "") for m in r.json().get("models", [])}
    missing = [
        m
        for m in (settings.ollama_model, settings.ollama_model_accurate)
        if m and m not in installed
    ]
    if missing:
        return False, "не скачаны модели — выполните: " + "; ".join(
            f"ollama pull {m}" for m in missing
        )
    return True, f"работает, модели: {settings.ollama_model}, {settings.ollama_model_accurate}"


def cmd_doctor(_args: argparse.Namespace) -> int:
    settings = get_settings()
    print(f"lms-tool {__version__}, Python {sys.version.split()[0]}, {sys.platform}")
    print(f"Каталог настроек: {user_config_dir()}")
    env_file = user_config_dir() / ".env"
    if not env_file.exists():
        print("[--] Файла настроек нет — создайте его: lms-tool init")
    print(f"[{'OK' if autostart.is_enabled() else '--'}] Автозапуск: "
          f"{'включён' if autostart.is_enabled() else 'выключен (lms-tool autostart on)'}")

    server_ok, server_msg = _check_server(settings)
    print(f"[{'OK' if server_ok else '!!'}] Сервер: {server_msg}")

    sources: list[tuple[str, Callable[[Settings], tuple[bool, str]]]] = [
        ("Gemini", _check_gemini),
        ("OpenAI-совместимый API", _check_openai),
        ("Ollama (локальная модель)", _check_ollama),
    ]
    any_source = False
    for label, check in sources:
        ok, msg = check(settings)
        any_source = any_source or ok
        print(f"[{'OK' if ok else '--'}] {label}: {msg}")

    if not any_source:
        print(
            "[!!] Не настроен ни один источник ответов. Настройте любой из трёх выше "
            "или пользуйтесь ручным режимом расширения — ему сервер не нужен."
        )
    return 0 if server_ok and any_source else 1


def cmd_init(_args: argparse.Namespace) -> int:
    """Create the settings file once; never overwrite the user's edits."""
    env_file = user_config_dir() / ".env"
    if env_file.exists():
        print(f"Файл настроек уже есть: {env_file}")
        return 0
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text(ENV_TEMPLATE, encoding="utf-8")
    print(f"Создан файл настроек: {env_file}")
    print("Впишите в него ключ или включите локальную модель, затем: lms-tool doctor")
    return 0


def cmd_autostart(args: argparse.Namespace) -> int:
    if args.state == "on":
        path = autostart.enable()
        print(f"Автозапуск включён: {path}")
        print("Сервер будет стартовать при входе в систему. Код сопряжения: lms-tool pair")
    elif args.state == "off":
        print("Автозапуск выключен." if autostart.disable() else "Автозапуск не был включён.")
    else:
        print("Автозапуск включён." if autostart.is_enabled() else "Автозапуск выключен.")
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    from src import bench

    path = Path(args.questions)
    if not path.is_file():
        print(f"Файл не найден: {path}")
        return 2
    return bench.run(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lms-tool", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run", help="запустить сервер (по умолчанию)").set_defaults(func=cmd_run)
    sub.add_parser("pair", help="выдать новый код сопряжения").set_defaults(func=cmd_pair)
    sub.add_parser("doctor", help="проверить установку").set_defaults(func=cmd_doctor)
    sub.add_parser("init", help="создать файл настроек").set_defaults(func=cmd_init)
    auto_parser = sub.add_parser("autostart", help="запускать сервер при входе в систему")
    auto_parser.add_argument("state", choices=["on", "off", "status"])
    auto_parser.set_defaults(func=cmd_autostart)
    bench_parser = sub.add_parser("bench", help="сравнить модели на своих вопросах")
    bench_parser.add_argument("questions", help="файл .jsonl с вопросами и верными ответами")
    bench_parser.set_defaults(func=cmd_bench)
    args = parser.parse_args(argv)
    func: Callable[[argparse.Namespace], int] = getattr(args, "func", cmd_run)
    return func(args)


if __name__ == "__main__":
    sys.exit(main())
