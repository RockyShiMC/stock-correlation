"""网页版登录：单用户，账号密码从环境变量读取，会话保存在签名 Cookie 中。

环境变量：
- APP_USERNAME / APP_PASSWORD：登录账号与密码
- SECRET_KEY：会话 Cookie 签名密钥（足够长的随机字符串）
- COOKIE_SECURE：设为 true 时 Cookie 只走 HTTPS（部署在 Caddy 后面时开启）
"""
import hmac
import os
import time
from collections import defaultdict, deque
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse

SESSION_MAX_AGE = 7 * 86400
# 不需要登录就能访问的路径
PUBLIC_PATHS = {"/login", "/login.html", "/style.css"}
# 这些前缀是接口，未登录返回 401；其余视为页面，未登录跳转登录页
API_PREFIXES = ("/search", "/kline", "/analysis", "/logout", "/me", "/docs", "/openapi.json")

# 登录失败限流：同一 IP 在窗口期内失败次数上限
FAIL_WINDOW = 600
FAIL_LIMIT = 5
_failures: dict[str, deque] = defaultdict(deque)


class AuthConfigError(RuntimeError):
    pass


def settings() -> dict:
    cfg = {
        "username": os.getenv("APP_USERNAME", ""),
        "password": os.getenv("APP_PASSWORD", ""),
        "secret_key": os.getenv("SECRET_KEY", ""),
        "cookie_secure": os.getenv("COOKIE_SECURE", "false").lower() in ("1", "true", "yes"),
    }
    missing = [k for k in ("APP_USERNAME", "APP_PASSWORD", "SECRET_KEY") if not os.getenv(k)]
    if missing:
        raise AuthConfigError(f"未设置环境变量：{', '.join(missing)}（见 backend/.env.example）")
    if len(cfg["secret_key"]) < 32:
        raise AuthConfigError("SECRET_KEY 至少 32 个字符")
    return cfg


def check_credentials(username: str, password: str) -> bool:
    cfg = settings()
    ok_user = hmac.compare_digest(username.encode(), cfg["username"].encode())
    ok_pass = hmac.compare_digest(password.encode(), cfg["password"].encode())
    return ok_user and ok_pass


def _prune(ip: str, now: float) -> deque:
    q = _failures[ip]
    while q and now - q[0] > FAIL_WINDOW:
        q.popleft()
    return q


def is_locked(ip: str) -> bool:
    return len(_prune(ip, time.time())) >= FAIL_LIMIT


def record_failure(ip: str) -> None:
    now = time.time()
    _prune(ip, now).append(now)


def clear_failures(ip: str) -> None:
    _failures.pop(ip, None)


def client_ip(request: Request) -> str:
    # 部署在 Caddy 后面时，uvicorn 以 --proxy-headers 运行，client.host 已是真实 IP
    return request.client.host if request.client else "unknown"


async def require_login(request: Request, call_next):
    path = request.url.path
    if path in PUBLIC_PATHS or request.session.get("user"):
        return await call_next(request)
    # 按路径段匹配，避免 /analysis.html 这类页面被当成 /analysis 接口
    if any(path == p or path.startswith(p + "/") for p in API_PREFIXES):
        return JSONResponse({"detail": "未登录"}, status_code=401)
    target = path + (f"?{request.url.query}" if request.url.query else "")
    return RedirectResponse(f"/login.html?next={quote(target, safe='')}", status_code=303)
