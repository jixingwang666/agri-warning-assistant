const API_BASE = "http://127.0.0.1:8000";

const { createApp, nextTick } = Vue;

const app = createApp({
  data() {
    return {
      activeView: "dashboard",
      loading: false,
      error: "",
      isLoggedIn: localStorage.getItem("agri_logged_in") === "1",
      loginForm: { username: "", password: "" },
      loginError: "",
      overview: {},
      categories: [],
      hotwords: [],
      priceTrend: [],
      news: [],
      warnings: [],
      prices: [],
      selectedNews: null,
      uploadFile: null,
      uploadResult: "",
      searchKeywords: "",
      filters: { keyword: "", category: "", region: "" },
      warningFilters: { risk_level: "", region: "", product: "" },
      priceFilters: { product_name: "", region: "" },
    };
  },
  computed: {
    viewTitle() {
      return {
        dashboard: "农业舆情总览",
        news: "新闻分析",
        warnings: "风险预警",
        prices: "价格趋势",
        import: "数据导入",
      }[this.activeView];
    },
    statusText() {
      return this.loading ? "正在同步数据" : "数据来自本地 MySQL 与后端分析接口";
    },
  },
  watch: {
    activeView() {
      nextTick(() => this.renderCharts());
    },
  },
  async mounted() {
    if (this.isLoggedIn) {
      await this.refreshAll();
    }
  },
  methods: {
    async request(path, options = {}) {
      const response = await fetch(`${API_BASE}${path}`, options);
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `请求失败: ${response.status}`);
      }
      return response.json();
    },
    async login() {
      this.loading = true;
      this.loginError = "";
      try {
        await this.request("/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(this.loginForm),
        });
        localStorage.setItem("agri_logged_in", "1");
        this.isLoggedIn = true;
        this.loginForm.password = "";
        await this.refreshAll();
      } catch (err) {
        this.loginError = "用户名或密码错误";
      } finally {
        this.loading = false;
      }
    },
    logout() {
      localStorage.removeItem("agri_logged_in");
      this.isLoggedIn = false;
      this.activeView = "dashboard";
    },
    async refreshAll() {
      this.loading = true;
      this.error = "";
      try {
        await Promise.all([
          this.loadOverview(),
          this.loadNews(),
          this.loadWarnings(),
          this.loadPrices(),
          this.loadCharts(),
        ]);
        await nextTick();
        this.renderCharts();
      } catch (err) {
        this.error = `无法加载数据：${err.message}`;
      } finally {
        this.loading = false;
      }
    },
    async loadOverview() {
      this.overview = await this.request("/api/stats/overview");
    },
    async loadNews() {
      const params = new URLSearchParams();
      Object.entries(this.filters).forEach(([key, value]) => value && params.append(key, value));
      params.append("limit", "50");
      this.news = await this.request(`/api/news?${params.toString()}`);
      if (!this.selectedNews && this.news.length) this.selectedNews = this.news[0];
    },
    async loadWarnings() {
      const params = new URLSearchParams();
      Object.entries(this.warningFilters).forEach(([key, value]) => value && params.append(key, value));
      params.append("limit", "50");
      this.warnings = await this.request(`/api/warnings?${params.toString()}`);
    },
    async loadPrices() {
      const params = new URLSearchParams();
      Object.entries(this.priceFilters).forEach(([key, value]) => value && params.append(key, value));
      this.prices = await this.request(`/api/prices?${params.toString()}`);
    },
    async loadCharts() {
      const [categories, hotwords, priceTrend] = await Promise.all([
        this.request("/api/charts/category"),
        this.request("/api/charts/hotwords?limit=12"),
        this.request("/api/charts/price-trend"),
      ]);
      this.categories = categories;
      this.hotwords = hotwords;
      this.priceTrend = priceTrend;
    },
    async crawlNews() {
      this.loading = true;
      this.error = "";
      try {
        const result = await this.request("/api/crawl/update?limit_per_source=5", { method: "POST" });
        await this.refreshAll();
        this.error = `联网更新完成：抓取 ${result.crawled} 条，保存新闻 ${result.news_saved} 条，生成预警 ${result.warnings_saved} 条。`;
      } catch (err) {
        this.error = `联网更新失败：${err.message}`;
      } finally {
        this.loading = false;
      }
    },
    async searchCrawl() {
      this.loading = true;
      this.error = "";
      try {
        const kw = encodeURIComponent(this.searchKeywords.trim());
        const url = `/api/crawl/search?limit_per_query=5${kw ? `&keywords=${kw}` : ""}`;
        const result = await this.request(url, { method: "POST" });
        await this.refreshAll();
        this.error = `关键词采集完成：抓取 ${result.crawled} 条，保存新闻 ${result.news_saved} 条，生成预警 ${result.warnings_saved} 条。`;
      } catch (err) {
        this.error = `关键词采集失败：${err.message}`;
      } finally {
        this.loading = false;
      }
    },
    onFileChange(event) {
      this.uploadFile = event.target.files[0] || null;
      this.uploadResult = "";
    },
    async uploadNews() {
      if (!this.uploadFile) return;
      const formData = new FormData();
      formData.append("file", this.uploadFile);
      try {
        const result = await this.request("/api/import/news", {
          method: "POST",
          body: formData,
        });
        this.uploadResult = JSON.stringify(result, null, 2);
      } catch (err) {
        this.uploadResult = err.message;
      }
    },
    splitWords(value) {
      return String(value || "").split("、").filter(Boolean);
    },
    levelClass(level) {
      if (level === "高风险" || level === "较高风险") return "high";
      if (level === "中风险") return "mid";
      return "low";
    },
    scoreParts(item) {
      return [
        { key: "keyword", name: "关键词分", value: this.toScore(item.keyword_score), max: 60 },
        { key: "price", name: "价格分", value: this.toScore(item.price_score), max: 25 },
        { key: "heat", name: "热度分", value: this.toScore(item.heat_score), max: 15 },
        { key: "region", name: "地区分", value: this.toScore(item.region_score), max: 12 },
        { key: "stable", name: "稳定降分", value: this.toScore(item.positive_adjustment), max: 18, deduct: true },
      ];
    },
    toScore(value) {
      const number = Number(value || 0);
      return Number.isFinite(number) ? number : 0;
    },
    scoreWidth(value, max) {
      const number = Math.max(0, Math.min(Number(value || 0), max));
      return `${Math.round((number / max) * 100)}%`;
    },
    renderCharts() {
      if (!window.echarts || this.activeView !== "dashboard") return;
      this.renderCategoryChart();
      this.renderHotwordChart();
      this.renderPriceChart();
    },
    renderCategoryChart() {
      const el = document.getElementById("categoryChart");
      if (!el) return;
      const chart = echarts.init(el);
      chart.setOption({
        tooltip: { trigger: "item" },
        series: [{
          type: "pie",
          radius: ["42%", "70%"],
          data: this.categories,
          label: { formatter: "{b}" },
        }],
      });
    },
    renderHotwordChart() {
      const el = document.getElementById("hotwordChart");
      if (!el) return;
      const chart = echarts.init(el);
      chart.setOption({
        grid: { left: 56, right: 16, top: 12, bottom: 28 },
        xAxis: { type: "value" },
        yAxis: { type: "category", data: this.hotwords.map(item => item.name).reverse() },
        series: [{
          type: "bar",
          data: this.hotwords.map(item => item.value).reverse(),
          itemStyle: { color: "#2f7d4f" },
        }],
      });
    },
    renderPriceChart() {
      const el = document.getElementById("priceChart");
      if (!el) return;
      const chart = echarts.init(el);
      const groups = {};
      this.priceTrend.forEach((item) => {
        const key = `${item.product_name}-${item.region}`;
        groups[key] ||= [];
        groups[key].push(item);
      });
      const dates = [...new Set(this.priceTrend.map(item => item.date))].sort();
      chart.setOption({
        tooltip: { trigger: "axis" },
        legend: { type: "scroll", bottom: 0 },
        grid: { left: 48, right: 18, top: 16, bottom: 56 },
        xAxis: { type: "category", data: dates },
        yAxis: { type: "value" },
        series: Object.entries(groups).map(([name, rows]) => ({
          name,
          type: "line",
          smooth: true,
          data: dates.map(date => {
            const row = rows.find(item => item.date === date);
            return row ? Number(row.price) : null;
          }),
        })),
      });
    },
  },
});

if (window.ElementPlus) {
  app.use(ElementPlus);
}

app.mount("#app");
