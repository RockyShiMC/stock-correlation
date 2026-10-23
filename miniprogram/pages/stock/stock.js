import * as echarts from '../../components/ec-canvas/echarts'

const api = require('../../utils/api')
const { DAYS } = require('../../config')

const UP = '#e5383b'
const DOWN = '#1a9e5f'

function klineOption(items) {
  const dates = items.map((d) => d.date)
  // ECharts K 线数据顺序：开、收、低、高
  const candles = items.map((d) => [d.open, d.close, d.low, d.high])
  const volumes = items.map((d) => ({
    value: d.volume,
    itemStyle: { color: d.close >= d.open ? UP : DOWN }
  }))
  return {
    animation: false,
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' }, confine: true },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: [
      { left: 50, right: 12, top: 16, height: '58%' },
      { left: 50, right: 12, top: '76%', height: '16%' }
    ],
    xAxis: [
      { type: 'category', data: dates, boundaryGap: true, axisLabel: { fontSize: 10 } },
      { type: 'category', data: dates, gridIndex: 1, boundaryGap: true, axisLabel: { show: false }, axisTick: { show: false } }
    ],
    yAxis: [
      { scale: true, axisLabel: { fontSize: 10 }, splitLine: { lineStyle: { color: '#eef0f3' } } },
      { gridIndex: 1, axisLabel: { show: false }, splitLine: { show: false } }
    ],
    dataZoom: [{ type: 'inside', xAxisIndex: [0, 1], start: 0, end: 100 }],
    series: [
      {
        name: '日K',
        type: 'candlestick',
        data: candles,
        itemStyle: { color: UP, color0: DOWN, borderColor: UP, borderColor0: DOWN }
      },
      { name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: volumes }
    ]
  }
}

Page({
  data: {
    symbol: '',
    market: '',
    name: '',
    latest: null,
    loading: true,
    error: '',
    ec: { lazyLoad: true }
  },

  onLoad(options) {
    const symbol = decodeURIComponent(options.symbol || '')
    const name = decodeURIComponent(options.name || '')
    this.setData({ symbol, market: options.market, name })
    wx.setNavigationBarTitle({ title: name || symbol })
    this.load()
  },

  async load() {
    this.setData({ loading: true, error: '' })
    try {
      const res = await api.kline(this.data.symbol, this.data.market, DAYS)
      const items = res.items
      const last = items[items.length - 1]
      const prev = items.length > 1 ? items[items.length - 2] : null
      const change = prev ? last.close - prev.close : 0
      const pct = prev ? (change / prev.close) * 100 : 0
      this.setData({
        name: res.name,
        loading: false,
        latest: {
          date: last.date,
          close: last.close.toFixed(2),
          change: (change >= 0 ? '+' : '') + change.toFixed(2),
          pct: (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%',
          up: change >= 0
        },
        count: items.length
      }, () => this.renderChart(items))
    } catch (err) {
      this.setData({ loading: false, error: err.message })
    }
  },

  renderChart(items) {
    this.selectComponent('#kline').init((canvas, width, height, dpr) => {
      const chart = echarts.init(canvas, null, { width, height, devicePixelRatio: dpr })
      canvas.setChart(chart)
      chart.setOption(klineOption(items))
      return chart
    })
  }
})
