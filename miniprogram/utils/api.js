const { BASE_URL } = require('../config')

function request(path, { method = 'GET', data } = {}) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: BASE_URL + path,
      method,
      data,
      header: { 'Content-Type': 'application/json' },
      timeout: 60000,
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data)
        } else {
          const detail = res.data && res.data.detail
          reject(new Error(typeof detail === 'string' ? detail : `请求失败（${res.statusCode}）`))
        }
      },
      fail(err) {
        reject(new Error(err.errMsg || '网络错误'))
      }
    })
  })
}

module.exports = {
  search: (q) => request('/search', { data: { q } }),
  kline: (symbol, market, days) => request('/kline', { data: { symbol, market, days } }),
  createAnalysis: (a, b, days) => request('/analysis', { method: 'POST', data: { a, b, days } }),
  getAnalysis: (taskId) => request(`/analysis/${taskId}`)
}
