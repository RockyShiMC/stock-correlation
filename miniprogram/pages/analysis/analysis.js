import * as echarts from '../../components/ec-canvas/echarts'

const api = require('../../utils/api')
const { POLL_INTERVAL_MS, DAYS } = require('../../config')

const STATUS_TEXT = { pending: '排队中', running: '分析中' }
const CONFIDENCE_TEXT = { high: '高', medium: '中', low: '低' }

// 统计数字原样展示，不做二次计算
const fmt = (v) => (v === null || v === undefined ? '—' : String(v))

function buildView(result) {
  const s = result.stats
  const newsById = {}
  result.news.forEach((n) => { newsById[n.id] = n })
  return {
    a: s.a,
    b: s.b,
    stats: {
      pearson: fmt(s.correlation.pearson),
      spearman: fmt(s.correlation.spearman),
      sampleDays: s.aligned.sample_days,
      returnDays: s.aligned.return_days,
      range: `${s.aligned.first_date || '—'} ~ ${s.aligned.last_date || '—'}`,
      leadLag: s.lead_lag.applicable
        ? { applicable: true, desc: s.lead_lag.description, pearson: fmt(s.lead_lag.pearson), sampleDays: s.lead_lag.sample_days }
        : { applicable: false, desc: s.lead_lag.description },
      benchA: { index: s.benchmark.a.index_name, pearson: fmt(s.benchmark.a.pearson), sampleDays: s.benchmark.a.sample_days },
      benchB: { index: s.benchmark.b.index_name, pearson: fmt(s.benchmark.b.pearson), sampleDays: s.benchmark.b.sample_days }
    },
    chains: result.llm.logic_chains.map((c) => ({
      claim: c.claim,
      confidence: c.confidence,
      confidenceText: CONFIDENCE_TEXT[c.confidence] || c.confidence,
      evidence: c.evidence_ids.map((id) => newsById[id] || { id, title: '（未找到该新闻）' }),
      expanded: false
    })),
    summary: result.llm.summary,
    caveats: result.llm.caveats,
    newsNotes: result.news_notes || [],
    newsCount: result.news.length,
    generatedAt: result.generated_at
  }
}

function rollingOption(rolling) {
  return {
    animation: false,
    tooltip: { trigger: 'axis', confine: true },
    legend: { data: ['20日', '60日'], top: 0, textStyle: { fontSize: 11 } },
    grid: { left: 40, right: 12, top: 30, bottom: 28 },
    xAxis: { type: 'category', data: rolling.dates, axisLabel: { fontSize: 10 } },
    yAxis: {
      type: 'value', min: -1, max: 1, interval: 0.5,
      axisLabel: { fontSize: 10 }, splitLine: { lineStyle: { color: '#eef0f3' } }
    },
    series: [
      { name: '20日', type: 'line', data: rolling.w20, showSymbol: false, connectNulls: false, lineStyle: { width: 1.5 } },
      { name: '60日', type: 'line', data: rolling.w60, showSymbol: false, connectNulls: false, lineStyle: { width: 2 } }
    ],
    color: ['#2f63c9', '#e08a00']
  }
}

Page({
  data: {
    phase: 'submitting', // submitting | polling | done | failed
    statusText: '提交中',
    elapsed: 0,
    error: '',
    view: null,
    ec: { lazyLoad: true }
  },

  onLoad(options) {
    this.req = {
      a: { symbol: decodeURIComponent(options.aSymbol), market: options.aMarket },
      b: { symbol: decodeURIComponent(options.bSymbol), market: options.bMarket }
    }
    this.start()
  },

  onUnload() {
    this.stopped = true
    clearTimeout(this.timer)
    clearInterval(this.clock)
  },

  async start() {
    this.stopped = false
    clearInterval(this.clock)
    const t0 = Date.now()
    this.setData({ phase: 'submitting', statusText: '提交中', error: '', view: null, elapsed: 0 })
    this.clock = setInterval(() => this.setData({ elapsed: Math.round((Date.now() - t0) / 1000) }), 1000)
    try {
      const { task_id } = await api.createAnalysis(this.req.a, this.req.b, DAYS)
      this.taskId = task_id
      this.setData({ phase: 'polling' })
      this.poll()
    } catch (err) {
      this.fail(err.message)
    }
  },

  async poll() {
    if (this.stopped) return
    try {
      const task = await api.getAnalysis(this.taskId)
      if (this.stopped) return
      if (task.status === 'done') {
        clearInterval(this.clock)
        const result = task.result
        this.setData({ phase: 'done', view: buildView(result) }, () => this.renderChart(result.stats.rolling))
        return
      }
      if (task.status === 'failed') {
        this.fail(task.error || '分析失败')
        return
      }
      this.setData({ statusText: STATUS_TEXT[task.status] || task.status })
    } catch (err) {
      // 单次轮询失败不终止，下一轮继续
      this.setData({ statusText: `网络异常，重试中（${err.message}）` })
    }
    this.timer = setTimeout(() => this.poll(), POLL_INTERVAL_MS)
  },

  fail(message) {
    clearInterval(this.clock)
    this.setData({ phase: 'failed', error: message })
  },

  renderChart(rolling) {
    this.selectComponent('#rolling').init((canvas, width, height, dpr) => {
      const chart = echarts.init(canvas, null, { width, height, devicePixelRatio: dpr })
      canvas.setChart(chart)
      chart.setOption(rollingOption(rolling))
      return chart
    })
  },

  onToggleChain(e) {
    const i = e.currentTarget.dataset.index
    this.setData({ [`view.chains[${i}].expanded`]: !this.data.view.chains[i].expanded })
  },

  onCopyLink(e) {
    const url = e.currentTarget.dataset.url
    if (!url) return
    wx.setClipboardData({ data: url, success: () => wx.showToast({ title: '链接已复制', icon: 'none' }) })
  },

  onRetry() {
    this.start()
  }
})
