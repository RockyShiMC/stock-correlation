"""FastAPI 入口。

开发运行（在 backend 目录下）：
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
import logging
from contextlib import asynccontextmanager
from typing import Literal

from dotenv import load_dotenv

load_dotenv()  # 必须在导入读取环境变量的模块之前

from fastapi import FastAPI, HTTPException, Query  # noqa: E402
from fastapi.concurrency import run_in_threadpool  # noqa: E402
from pydantic import BaseModel, Field, field_validator  # noqa: E402

from app import tasks  # noqa: E402
from app.data import get_adapter, search_all  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    tasks.recover_interrupted()
    yield


app = FastAPI(title="股票逻辑相关性分析", lifespan=lifespan)


class Target(BaseModel):
    symbol: str
    market: Literal["CN", "US"]

    @field_validator("market", mode="before")
    @classmethod
    def _upper_market(cls, v):
        return str(v).strip().upper()

    @field_validator("symbol")
    @classmethod
    def _clean_symbol(cls, v: str) -> str:
        v = v.strip().upper()
        if not v:
            raise ValueError("symbol 不能为空")
        return v


class AnalysisRequest(BaseModel):
    a: Target
    b: Target
    days: int = Field(120, ge=30, le=500)


@app.get("/search")
async def search(q: str = Query(..., min_length=1)):
    try:
        return await run_in_threadpool(search_all, q)
    except Exception as e:  # noqa: BLE001
        log.exception("搜索失败")
        raise HTTPException(502, f"数据源错误：{e}") from e


@app.get("/kline")
async def kline(symbol: str, market: str, days: int = Query(120, ge=1, le=1000)):
    try:
        adapter = get_adapter(market)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    symbol = symbol.strip().upper()

    def load():
        df = adapter.kline(symbol, days)
        return adapter.name_of(symbol), df

    try:
        name, df = await run_in_threadpool(load)
    except Exception as e:  # noqa: BLE001
        log.exception("日 K 获取失败")
        raise HTTPException(502, f"数据源错误：{e}") from e
    if df.empty:
        raise HTTPException(404, "没有日 K 数据")
    return {
        "symbol": symbol,
        "market": adapter.market,
        "name": name or symbol,
        "items": df.to_dict(orient="records"),
    }


@app.post("/analysis")
async def create_analysis(req: AnalysisRequest):
    task_id = await run_in_threadpool(
        tasks.submit, req.a.model_dump(), req.b.model_dump(), req.days
    )
    return {"task_id": task_id}


@app.get("/analysis/{task_id}")
async def get_analysis(task_id: str):
    task = await run_in_threadpool(tasks.get, task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")
    return task
