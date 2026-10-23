# 股票逻辑相关性分析 · 网页版（web 分支）

仅供个人研究，不构成投资建议。

> 本分支在小程序版（`main` 分支）基础上增加了**浏览器网页版**：后端直接托管网页，用浏览器登录后即可使用。
> 所有接口和页面都需要登录，因此本分支下小程序无法直接调用接口；小程序请使用 `main` 分支。

## 网页版快速开始（本机）

1. 安装依赖：见下方“后端（开发环境）”。
2. 配置 `backend/.env`（参考 `backend/.env.example`）：
   - `ANTHROPIC_MODEL`（`ANTHROPIC_API_KEY` 可用系统环境变量）
   - `APP_USERNAME`、`APP_PASSWORD`：登录账号密码
   - `SECRET_KEY`：会话签名密钥，至少 32 个字符，生成：`python -c "import secrets; print(secrets.token_urlsafe(48))"`
   - `COOKIE_SECURE=false`（本机 http 访问）
3. 启动（在 `backend` 目录下）：
   ```bash
   .venv/Scripts/python -m uvicorn app.main:app --host 0.0.0.0 --port 8800
   ```
4. 浏览器打开 <http://127.0.0.1:8800>，登录后使用。同一 Wi-Fi 下的手机可直接用浏览器访问 `http://电脑局域网IP:8800`（需 Windows 防火墙放行 8800 端口）。

说明：
- 页面：首页（搜索、选两个标的）、个股页（最新价、日 K）、分析页（每 3 秒轮询，统计卡片、滚动相关图、逻辑链可展开查看引用新闻并跳转原文），分析页底部固定免责声明。
- 端口用 8800 是因为本机 8000 已被其他 Docker 容器占用；没有冲突的话用任意端口均可。
- 登录：单用户，会话 Cookie 有效期 7 天；同一 IP 10 分钟内登录失败 5 次会被暂时锁定。
- ECharts 5.5.1 本地托管在 `backend/app/web/vendor/`（Apache-2.0），不依赖 CDN。

## 后端（开发环境）

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows；Linux/macOS 用 .venv/bin/python
cp .env.example .env
```

### 数据层验证（阶段 1）

```bash
cd backend
.venv/Scripts/python -m scripts.verify_stage1
```

首次运行会拉取美股符号表（新浪接口逐页抓取，约 10 分钟），结果缓存在 SQLite（`backend/data.db`），A 股符号表缓存 1 天、美股 7 天。

### 统计层验证（阶段 2）

```bash
cd backend
.venv/Scripts/python -m pytest -q tests
.venv/Scripts/python -m scripts.verify_stage2
```

统计口径见 `backend/app/analysis/stats.py` 顶部注释。

### 启动 API 服务（阶段 3）

`.env` 中需要 `ANTHROPIC_MODEL`（如 `claude-opus-5-5`）；`ANTHROPIC_API_KEY` 可写在 `.env`，或直接用系统环境变量。

```bash
cd backend
.venv/Scripts/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

| 接口 | 说明 |
|---|---|
| `GET /search?q=` | 按名称或代码搜索，返回 `[{symbol, name, market}]` |
| `GET /kline?symbol=&market=&days=120` | `{symbol, market, name, items:[{date, open, high, low, close, volume}]}` |
| `POST /analysis` | body `{a:{symbol,market}, b:{symbol,market}, days:120}` → `{task_id}` |
| `GET /analysis/{task_id}` | `{status: pending\|running\|done\|failed, result?, error?}` |

完整分析示例：

```bash
curl -s -X POST http://127.0.0.1:8000/analysis -H "Content-Type: application/json" -d '{"a":{"symbol":"600667","market":"CN"},"b":{"symbol":"GOOGL","market":"US"},"days":120}'
```

```bash
curl -s http://127.0.0.1:8000/analysis/<task_id>
```

- `result = {stats, llm, news, news_notes, generated_at}`；`news_notes` 用于注明“美股新闻源未接入”等数据缺口。
- 同一对标的（A/B 顺序相关）、同一 days、同一北京时间自然日内重复请求，直接返回已完成的任务；失败任务不缓存。
- 大模型结构化输出：`submit_analysis` 工具 + `strict: true`。claude-opus-5-5 不支持强制 `tool_choice`，所以用 `auto` 并在 prompt 中要求调用；未调用工具或 pydantic 校验失败时重试 1 次，仍失败则任务 failed。
- Windows Git Bash 下 curl 的 `--data-urlencode` 会把中文按 GBK 编码，搜索中文请手动写 UTF-8 百分号编码，如 `q=%E8%B0%B7%E6%AD%8C`（谷歌）。

## 小程序（阶段 4）

- 工程目录：`miniprogram/`，用微信开发者工具“导入项目”选择该目录。
- `project.config.json` 中 `appid` 为 `touristappid`（游客模式），发布体验版前换成自己的小程序 AppID。
- 后端地址集中在 `miniprogram/config.js` 的 `BASE_URL`（当前为线上地址占位，本机开发改回 `http://127.0.0.1:8000`）。
- 开发者工具中勾选“详情 → 本地设置 → 不校验合法域名、web-view（业务域名）、TLS 版本以及 HTTPS 证书”。
- 图表使用 [echarts-for-weixin](https://github.com/ecomfe/echarts-for-weixin) 的 `ec-canvas` 组件（内置 ECharts 5.3.3，BSD-3 许可），位于 `miniprogram/components/ec-canvas/`。
- 手机真机预览时，后端需用 `--host 0.0.0.0` 启动，`BASE_URL` 改为电脑的局域网 IP（如 `http://192.168.1.10:8000`）。

### 不部署服务器的本地试用

后端跑在自己电脑上即可，前提是这台电脑能访问 Anthropic API（大陆网络需要代理）。

1. 启动后端：`cd backend` 后运行 `.venv/Scripts/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`，窗口保持打开。
2. 只在电脑上用：`BASE_URL` 设为 `http://127.0.0.1:8000`，在开发者工具模拟器中使用。
3. 在手机上用：
   - 手机和电脑连同一个 Wi-Fi；`BASE_URL` 改为电脑局域网 IP，如 `http://192.168.1.10:8000`。
   - Windows 防火墙需允许 8000 端口入站（首次启动时弹窗选“允许”，或在“高级安全 Windows Defender 防火墙”中添加入站规则）。
   - 开发者工具点“预览”扫码，或“真机调试”；手机上在小程序右上角菜单打开“开发调试”，否则 http 地址会被拦截。
   - 手机只能在电脑开着、后端运行时使用。

## 数据源说明（akshare 1.19.1 实测）

| 用途 | A 股 | 美股 |
|---|---|---|
| 搜索符号表 | `stock_info_sh_name_code`（主板A股、科创板）、`stock_info_sz_name_code` | `get_us_stock_name`（含中文名） |
| 日 K | `stock_zh_a_hist_tx`（主）、`stock_zh_a_hist`（备） | `stock_us_daily` |
| 大盘指数 | `stock_zh_index_daily("sh000300")` 沪深 300 | `index_us_stock_sina(".NDX")` 纳斯达克 100 |

- 日 K 均为前复权，成交量单位统一为“股”。
- 北交所暂未纳入搜索（`stock_info_bj_name_code` 在开发网络下不可用）。

## 部署到香港 / 海外服务器（阶段 5）

Anthropic API 不对中国大陆提供服务，后端部署在香港或海外云服务器上（不使用微信云托管）。架构：`Caddy（443，自动 HTTPS）→ backend（FastAPI，容器内 8000）`，SQLite 存在 Docker 卷 `backend_data` 中。

### 需要配置的环境变量

| 文件 | 变量 | 说明 |
|---|---|---|
| 根目录 `.env` | `DOMAIN` | 已解析到服务器公网 IP 的域名，如 `api.example.com`；Caddy 用它向 Let's Encrypt 申请证书。缺少时 `docker compose` 直接报错 |
| `backend/.env` | `ANTHROPIC_API_KEY` | Claude API 密钥，**必填** |
| `backend/.env` | `ANTHROPIC_MODEL` | 模型名，如 `claude-opus-5-5`，**必填** |
| `backend/.env` | `DB_PATH` | 无需填写，compose 中已固定为 `/data/data.db` |
| `backend/.env` | `APP_USERNAME` / `APP_PASSWORD` | 网页版登录账号密码，**必填**，请用强密码 |
| `backend/.env` | `SECRET_KEY` | 会话签名密钥，至少 32 个字符，**必填** |
| `backend/.env` | `COOKIE_SECURE` | 无需填写，compose 中已设为 `true`（Cookie 只走 HTTPS） |

### 步骤

1. **准备服务器**：香港或海外地区，Linux（如 Ubuntu 22.04+），建议 1 核 2G 以上。安全组 / 防火墙放行 TCP 80、443（以及 UDP 443，用于 HTTP/3，可选）。
2. **域名解析**：添加 A 记录，把 `DOMAIN` 指向服务器公网 IP，等解析生效（`ping 你的域名` 能看到该 IP）。
3. **安装 Docker**（含 compose 插件）：
   ```bash
   curl -fsSL https://get.docker.com | sh
   ```
4. **上传代码**：把 `backend/`（不含 `.venv`、`data.db`、`.env`）、`docker-compose.yml`、`Caddyfile`、`.env.example` 上传到服务器，如 `/opt/stock-correlation/`。
5. **填写环境变量**：
   ```bash
   cd /opt/stock-correlation
   cp .env.example .env                    # 填 DOMAIN
   cp backend/.env.example backend/.env    # 填 ANTHROPIC_API_KEY、ANTHROPIC_MODEL
   chmod 600 backend/.env
   ```
6. **启动**：
   ```bash
   docker compose up -d --build
   docker compose logs -f caddy            # 看到证书申请成功（certificate obtained successfully）即可
   ```
7. **验证**：浏览器打开 `https://你的域名`，应跳转到登录页；登录后搜索 `600667` 能出结果。
8. **预热美股代码表**：第一次搜索美股（如 `GOOGL`）时后端需下载美股代码表，约 10 分钟，页面会一直显示“搜索中”，耐心等待即可，之后缓存 7 天。

### 运维

```bash
docker compose logs -f backend          # 后端日志
docker compose up -d --build            # 更新代码后重建
docker compose down                     # 停止（数据卷保留）
```

### 注意

- web 分支所有页面和接口都需要登录；部署后浏览器访问 `https://你的域名` 即可。登录密码请设置得足够强。
- AKShare 的数据源都是国内网站，海外服务器访问可能变慢或被限流；部署后先用第 7、8 步确认 A 股和美股接口都能取到数据。
