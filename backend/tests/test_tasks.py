import importlib
import time

import pytest


@pytest.fixture()
def tasks(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.db"))
    import app.db
    importlib.reload(app.db)
    import app.tasks
    importlib.reload(app.tasks)
    yield app.tasks
    importlib.reload(app.db)


A = {"symbol": "600667", "market": "CN"}
B = {"symbol": "GOOGL", "market": "US"}


def wait(tasks, task_id, timeout=5):
    t0 = time.time()
    while time.time() - t0 < timeout:
        t = tasks.get(task_id)
        if t["status"] in ("done", "failed"):
            return t
        time.sleep(0.05)
    raise AssertionError("任务超时")


def test_cache_key_is_per_day_and_ordered(tasks):
    assert tasks.cache_key(A, B, 120, "2026-10-23") != tasks.cache_key(A, B, 120, "2026-10-24")
    assert tasks.cache_key(A, B, 120, "2026-10-23") != tasks.cache_key(B, A, 120, "2026-10-23")
    assert tasks.cache_key({"symbol": "googl", "market": "us"}, A, 120, "d") == tasks.cache_key(B, A, 120, "d")


def test_same_pair_same_day_returns_cached_task(tasks):
    calls = []

    def runner(a, b, days):
        calls.append(1)
        return {"ok": True}

    t1 = tasks.submit(A, B, 120, runner)
    assert wait(tasks, t1) == {"status": "done", "result": {"ok": True}}
    t2 = tasks.submit(A, B, 120, runner)
    assert t2 == t1
    assert len(calls) == 1


def test_failed_task_is_not_cached(tasks):
    def boom(a, b, days):
        raise RuntimeError("x")

    t1 = tasks.submit(A, B, 120, boom)
    out = wait(tasks, t1)
    assert out["status"] == "failed" and "RuntimeError" in out["error"]
    t2 = tasks.submit(A, B, 120, lambda a, b, d: {"ok": 1})
    assert t2 != t1


def test_invalid_market_rejected(tasks):
    with pytest.raises(ValueError):
        tasks.submit({"symbol": "X", "market": "HK"}, B, 120, lambda *a: {})
