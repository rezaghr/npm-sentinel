import signal
from types import SimpleNamespace

import pytest

from app.scheduler import main as scheduler_main


class _TickResult:
    checked_count = 1
    enqueued_new_count = 0
    enqueued_updated_count = 0
    unchanged_count = 1
    skipped_running_count = 0
    failed_count = 0


@pytest.mark.anyio
async def test_run_scheduler_stops_on_shutdown_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    handlers: dict[int, object] = {}
    execute_calls = {"count": 0}

    class FakeMonitorUseCase:
        async def execute_once(self):
            execute_calls["count"] += 1
            shutdown_handler = handlers[signal.SIGTERM]
            shutdown_handler(signal.SIGTERM, None)
            return _TickResult()

    async def fake_check_database_connection(database_url: str | None = None) -> None:
        return None

    monkeypatch.setattr(scheduler_main, "get_settings", lambda: SimpleNamespace(
        service_name="scheduler-test",
        database_url="postgresql+psycopg://unused",
        scheduler_interval_seconds=10,
    ))
    monkeypatch.setattr(scheduler_main, "configure_logging", lambda settings: None)
    monkeypatch.setattr(scheduler_main, "check_database_connection", fake_check_database_connection)
    monkeypatch.setattr(scheduler_main, "_build_monitor_use_case", lambda: FakeMonitorUseCase())
    monkeypatch.setattr(scheduler_main.signal, "signal", lambda sig, handler: handlers.__setitem__(sig, handler))

    await scheduler_main.run_scheduler()

    assert execute_calls["count"] == 1


@pytest.mark.anyio
async def test_run_scheduler_continues_after_tick_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    handlers: dict[int, object] = {}
    execute_calls = {"count": 0}

    class FakeMonitorUseCase:
        async def execute_once(self):
            execute_calls["count"] += 1
            if execute_calls["count"] == 1:
                raise RuntimeError("tick failure")
            shutdown_handler = handlers[signal.SIGTERM]
            shutdown_handler(signal.SIGTERM, None)
            return _TickResult()

    async def fake_check_database_connection(database_url: str | None = None) -> None:
        return None

    async def fake_wait_for(awaitable, timeout: float):
        close = getattr(awaitable, "close", None)
        if callable(close):
            close()
        raise TimeoutError

    monkeypatch.setattr(scheduler_main, "get_settings", lambda: SimpleNamespace(
        service_name="scheduler-test",
        database_url="postgresql+psycopg://unused",
        scheduler_interval_seconds=10,
    ))
    monkeypatch.setattr(scheduler_main, "configure_logging", lambda settings: None)
    monkeypatch.setattr(scheduler_main, "check_database_connection", fake_check_database_connection)
    monkeypatch.setattr(scheduler_main, "_build_monitor_use_case", lambda: FakeMonitorUseCase())
    monkeypatch.setattr(scheduler_main.signal, "signal", lambda sig, handler: handlers.__setitem__(sig, handler))
    monkeypatch.setattr(scheduler_main.asyncio, "wait_for", fake_wait_for)

    await scheduler_main.run_scheduler()

    assert execute_calls["count"] == 2
