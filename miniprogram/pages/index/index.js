const api = require('../../utils/api')

const key = (item) => `${item.market}:${item.symbol}`

Page({
  data: {
    query: '',
    results: [],
    loading: false,
    searched: false,
    error: '',
    selected: [] // 最多两个
  },

  onInput(e) {
    this.setData({ query: e.detail.value })
  },

  async onSearch() {
    const q = this.data.query.trim()
    if (!q) return
    this.setData({ loading: true, error: '', searched: true })
    try {
      const results = await api.search(q)
      this.setData({ results: this.markSelected(results) })
    } catch (err) {
      this.setData({ error: err.message, results: [] })
    } finally {
      this.setData({ loading: false })
    }
  },

  markSelected(results) {
    const keys = this.data.selected.map(key)
    return results.map((r) => ({ ...r, checked: keys.includes(key(r)) }))
  },

  onToggle(e) {
    const item = this.data.results[e.currentTarget.dataset.index]
    let selected = this.data.selected.slice()
    const i = selected.findIndex((s) => key(s) === key(item))
    if (i >= 0) {
      selected.splice(i, 1)
    } else if (selected.length >= 2) {
      wx.showToast({ title: '最多选择两个标的', icon: 'none' })
      return
    } else {
      selected.push({ symbol: item.symbol, name: item.name, market: item.market })
    }
    this.setData({ selected }, () => this.setData({ results: this.markSelected(this.data.results) }))
  },

  onRemove(e) {
    const selected = this.data.selected.slice()
    selected.splice(e.currentTarget.dataset.index, 1)
    this.setData({ selected }, () => this.setData({ results: this.markSelected(this.data.results) }))
  },

  onDetail(e) {
    const item = this.data.results[e.currentTarget.dataset.index]
    wx.navigateTo({
      url: `/pages/stock/stock?symbol=${encodeURIComponent(item.symbol)}&market=${item.market}&name=${encodeURIComponent(item.name)}`
    })
  },

  onCompare() {
    const [a, b] = this.data.selected
    if (!a || !b) return
    const q = (p, s) => `${p}Symbol=${encodeURIComponent(s.symbol)}&${p}Market=${s.market}`
    wx.navigateTo({ url: `/pages/analysis/analysis?${q('a', a)}&${q('b', b)}` })
  }
})
