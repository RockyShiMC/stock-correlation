// 网页版公共工具：请求封装、DOM 构造、顶栏。
// 所有来自接口的文本都用 textContent 写入，不拼 HTML，避免新闻标题等外部内容注入脚本。

const POLL_INTERVAL_MS = 3000;
const DAYS = 120;

async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) {
    location.href = "/login.html?next=" + encodeURIComponent(location.pathname + location.search);
    throw new Error("未登录");
  }
  let data = null;
  try { data = await res.json(); } catch (_) { /* 非 JSON 响应 */ }
  if (!res.ok) {
    const detail = data && data.detail;
    throw new Error(typeof detail === "string" ? detail : `请求失败（${res.status}）`);
  }
  return data;
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

function marketTag(market, text) {
  return el("span", { class: `tag tag-${market}` }, text || market);
}

function query() {
  return new URLSearchParams(location.search);
}

// 只允许 http(s) 链接，防止 javascript: 之类的地址
function safeUrl(url) {
  try {
    const u = new URL(url);
    return u.protocol === "http:" || u.protocol === "https:" ? u.href : null;
  } catch (_) {
    return null;
  }
}

async function renderTopbar() {
  const bar = el("div", { class: "topbar" },
    el("a", { class: "brand", href: "/" }, "逻辑相关性分析"),
    el("span", { class: "spacer" }));
  document.body.prepend(bar);
  try {
    const me = await api("/me");
    bar.append(
      el("span", { class: "user" }, me.user || ""),
      el("button", {
        class: "link",
        onclick: async () => {
          await api("/logout", { method: "POST" });
          location.href = "/login.html";
        },
      }, "退出登录"));
  } catch (_) { /* 未登录时 api() 已跳转 */ }
}

function storageGet(key, fallback) {
  try {
    const v = sessionStorage.getItem(key);
    return v ? JSON.parse(v) : fallback;
  } catch (_) {
    return fallback;
  }
}

function storageSet(key, value) {
  try { sessionStorage.setItem(key, JSON.stringify(value)); } catch (_) { /* 隐私模式等 */ }
}
