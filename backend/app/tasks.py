"""异步分析任务与缓存（SQLite）。

- 缓存键：A、B 的 (market, symbol)、days、北京时间自然日。顺序有关：A/B 互换视为不同请求。
- 同一自然日内已有 done 任务 → 直接返回该任务；已有 pending/running 任务 → 返回同一个任务，不重复计算。
- failed 的任务不作为缓存，下次请求重新计算。
- 任务在线程池中执行（AKShare 与 SDK 都是同步调用）。
"""
import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from app.analysis import llm
from app.analysis.stats import collect_stats
from app.data import get_adapter
from app.data.news import get_news
from app.db import connect

log = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="analysis")
CN_TZ = ZoneInfo("Asia/Shanghai")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def cache_key(a: dict, b: dict, days: int, today: str | None = None) -> str:
    today = today or datetime.now(CN_TZ).strftime("%Y-%m-%d")
    return f"{a['market'].upper()}:{a['symbol'].upper()}|{b['market'].upper()}:{b['symbol'].upper()}|{days}|{today}"


def run_analysis(a: dict, b: dict, days: int) -> dict:
    """完整执行两层分析，返回 result。"""
    stats = collect_stats(a, b, days)

    news: list[dict] = []
    notes: list[str] = []
    for side in (stats["a"], stats["b"]):
        items, note = get_news(side["symbol"], side["market"])
        if note and note not in notes:
            notes.append(note)
        for item in items:
            news.append({
                "id": f"N{len(news) + 1}",
                "symbol": side["symbol"],
                "market": side["market"],
                "name": side["name"],
                **item,
            })

    analysis = llm.analyze(stats, news, notes)
    return {
        "stats": stats,
        "llm": analysis,
        "news": news,
        "news_notes": notes,
        "generated_at": _now(),
    }


def _update(task_id: str, **fields) -> None:
    fields["updated_at"] = _now()
    cols = ", ".join(f"{k}=?" for k in fields)
    with connect() as conn:
        conn.execute(f"UPDATE tasks SET {cols} WHERE task_id=?", (*fields.values(), task_id))


def _worker(task_id: str, a: dict, b: dict, days: int, runner: Callable[[dict, dict, int], dict]) -> None:
    _update(task_id, status="running")
    try:
        result = runner(a, b, days)
    except Exception as e:  # noqa: BLE001 - 任何失败都记到任务上
        log.exception("任务 %s 失败", task_id)
        _update(task_id, status="failed", error=f"{type(e).__name__}: {e}")
        return
    _update(task_id, status="done", result=json.dumps(result, ensure_ascii=False))


def submit(a: dict, b: dict, days: int, runner: Callable[[dict, dict, int], dict] = run_analysis) -> str:
    # 先校验市场参数，非法请求不建任务
    get_adapter(a["market"])
    get_adapter(b["market"])
    key = cache_key(a, b, days)
    with connect() as conn:
        row = conn.execute(
            "SELECT task_id FROM tasks WHERE cache_key=? AND status IN ('done','running','pending') "
            "ORDER BY CASE status WHEN 'done' THEN 0 ELSE 1 END, created_at DESC LIMIT 1",
            (key,),
        ).fetchone()
        if row:
            return row["task_id"]
        task_id = uuid.uuid4().hex
        now = _now()
        conn.execute(
            "INSERT INTO tasks(task_id, cache_key, request, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (task_id, key, json.dumps({"a": a, "b": b, "days": days}), "pending", now, now),
        )
    _executor.submit(_worker, task_id, a, b, days, runner)
    return task_id


def get(task_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT status, result, error FROM tasks WHERE task_id=?", (task_id,)).fetchone()
    if not row:
        return None
    out: dict = {"status": row["status"]}
    if row["result"]:
        out["result"] = json.loads(row["result"])
    if row["error"]:
        out["error"] = row["error"]
    return out


def recover_interrupted() -> None:
    """服务重启时，把上次没跑完的任务标记为 failed。"""
    with connect() as conn:
        conn.execute(
            "UPDATE tasks SET status='failed', error='服务重启，任务中断', updated_at=? "
            "WHERE status IN ('pending','running')",
            (_now(),),
        )
