// 后端地址集中在这里。
// 本机开发（开发者工具模拟器）：'http://127.0.0.1:8000'
// 手机真机：改为电脑的局域网 IP，如 'http://192.168.1.10:8000'
// 线上：改为部署时 DOMAIN 对应的 HTTPS 地址
module.exports = {
  BASE_URL: 'http://127.0.0.1:8000',
  POLL_INTERVAL_MS: 3000,
  DAYS: 120
}
