"""FastAPI 入口。接口之外还托管网页版前端（app/web），所有接口和页面都需要登录。

开发运行（在 backend 目录下）：
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

load_dotenv()  # 必须在导入读取环境变量的模块之前

from fastapi import FastAPI, HTTPException, Query, Request  # noqa: E402
from fastapi.concurrency import run_in_threadpool  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field, field_validator  # noqa: E402
from starlette.middleware.sessions import SessionMiddleware  # noqa: E402

from app import auth, tasks  # noqa: E402
from app.data import get_adapter, search_all  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

WEB_DIR = Path(__file__).resolve().parent / "web"
_auth_cfg = auth.settings()  # 缺少登录配置时直接启动失败


@asynccontextmanager
async def lifespan(_: FastAPI):
    tasks.recover_interrupted()
    yield


app = FastAPI(title="股票逻辑相关性分析", lifespan=lifespan)
app.middleware("http")(auth.require_login)
# 后添加的中间件在外层：先解析会话，再做登录校验
app.add_middleware(
    SessionMiddleware,
    secret_key=_auth_cfg["secret_key"],
    max_age=auth.SESSION_MAX_AGE,
    same_site="lax",
    https_only=_auth_cfg["cookie_secure"],
)


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/login")
async def login(req: LoginRequest, request: Request):
    ip = auth.client_ip(request)
    if auth.is_locked(ip):
        raise HTTPException(429, "登录失败次数过多，请 10 分钟后再试")
    if not auth.check_credentials(req.username, req.password):
        auth.record_failure(ip)
        raise HTTPException(401, "用户名或密码错误")
    auth.clear_failures(ip)
    request.session.clear()
    request.session["user"] = req.username
    return {"user": req.username}


@app.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/me")
async def me(request: Request):
    return {"user": request.session.get("user")}


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


# 网页前端放在最后挂载，接口路由优先匹配；访问 / 返回 index.html
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
