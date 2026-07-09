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
      pricePageTrend: [],
      news: [],
      warnings: [],
      prices: [],
      selectedNews: null,
      analysisModalOpen: false,
      analysisLoading: false,
      analysisError: "",
      selectedWarningAnalysis: null,
      uploadFile: null,
      uploadResult: "",
      searchKeywords: "",
      priceUploadFile: null,
      priceUploadResult: "",
      filters: { keyword: "", category: "", region: "" },
      warningFilters: { risk_level: "", region: "", product: "" },
      priceFilters: { product_name: "", city: "郑州" },
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
        this.loginError = err.message.includes("Failed to fetch")
          ? "无法连接后端服务，请确认后端已启动"
          : "用户名或密码错误";
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
      this.pricePageTrend = await this.request(`/api/charts/price-trend?${params.toString()}`);
      await nextTick();
      this.renderPricePageChart();
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
        const result = await this.request("/api/crawl/update?limit_per_source=5&total_limit=5", { method: "POST" });
        await this.refreshAll();
        const details = [];
        if (result.candidates !== undefined) details.push(`候选 ${result.candidates} 条`);
        if (result.skipped_existing) details.push(`已存在 ${result.skipped_existing} 条`);
        if (result.evidence_candidates !== undefined) details.push(`旁证候选 ${result.evidence_candidates} 条`);
        if ((result.errors || []).length || (result.evidence_errors || []).length) {
          details.push("部分来源访问失败");
        }
        this.error = `联网更新完成：保存农业新闻 ${result.news_saved} 条，生成预警 ${result.warnings_saved} 条。${details.length ? `（${details.join("，")}）` : ""}`;
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
        const url = `/api/crawl/search?limit_per_query=5&total_limit=5${kw ? `&keywords=${kw}` : ""}`;
        const result = await this.request(url, { method: "POST" });
        await this.refreshAll();
        const details = [];
        if (result.candidates !== undefined) details.push(`候选 ${result.candidates} 条`);
        if (result.skipped_existing) details.push(`已存在 ${result.skipped_existing} 条`);
        if ((result.errors || []).length || (result.evidence_errors || []).length) {
          details.push("部分来源访问失败");
        }
        this.error = `关键词采集完成：保存农业新闻 ${result.news_saved} 条，生成预警 ${result.warnings_saved} 条。${details.length ? `（${details.join("，")}）` : ""}`;
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
    onPriceFileChange(event) {
      this.priceUploadFile = event.target.files[0] || null;
      this.priceUploadResult = "";
    },
    async uploadNews() {
      if (!this.uploadFile) return;
      const formData = new FormData();
      formData.append("file", this.uploadFile);
      this.loading = true;
      this.error = "";
      try {
        const result = await this.request("/api/import/news", {
          method: "POST",
          body: formData,
        });
        this.warningFilters = { risk_level: "", region: "", product: "" };
        this.activeView = "warnings";
        this.uploadResult = `导入完成：读取 ${result.rows} 条新闻，保存 ${result.news_saved} 条，生成预警 ${result.warnings_saved} 条。`;
        this.error = this.uploadResult;
        await this.refreshAll();
      } catch (err) {
        this.uploadResult = err.message;
      } finally {
        this.loading = false;
      }
    },
    async uploadPrices() {
      if (!this.priceUploadFile) return;
      const formData = new FormData();
      formData.append("file", this.priceUploadFile);
      this.loading = true;
      this.error = "";
      try {
        const result = await this.request("/api/import/prices", {
          method: "POST",
          body: formData,
        });
        this.activeView = "prices";
        this.priceUploadResult = `价格导入完成：读取 ${result.rows} 条价格，保存 ${result.prices_saved} 条，重算预警/观察记录 ${result.warnings_saved} 条。`;
        this.error = this.priceUploadResult;
        await this.refreshAll();
      } catch (err) {
        this.priceUploadResult = err.message;
      } finally {
        this.loading = false;
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
        { key: "evidence", name: "证据分", value: this.toScore(item.evidence_score), max: 20 },
        { key: "region", name: "地区分", value: this.toScore(item.region_score), max: 20 },
        { key: "stable", name: "稳定降分", value: this.toScore(item.positive_adjustment), max: 18, deduct: true },
      ];
    },
    async openWarningAnalysis(item) {
      this.analysisModalOpen = true;
      this.analysisLoading = true;
      this.analysisError = "";
      this.selectedWarningAnalysis = null;
      try {
        this.selectedWarningAnalysis = await this.request(`/api/warnings/${item.id}/analysis`);
      } catch (err) {
        this.analysisError = `无法加载预警分析：${err.message}`;
      } finally {
        this.analysisLoading = false;
      }
    },
    closeWarningAnalysis() {
      this.analysisModalOpen = false;
      this.analysisError = "";
      this.selectedWarningAnalysis = null;
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
      if (!window.echarts) return;
      if (this.activeView === "dashboard") {
        this.renderCategoryChart();
        this.renderHotwordChart();
        this.renderPriceChart();
      }
      if (this.activeView === "prices") {
        this.renderPricePageChart();
      }
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
      this.renderLinePriceChart(el, this.priceTrend);
    },
    renderPricePageChart() {
      const el = document.getElementById("pricePageChart");
      if (!el) return;
      requestAnimationFrame(() => this.renderLinePriceChart(el, this.pricePageTrend));
    },
    renderLinePriceChart(el, rows) {
      const chart = echarts.getInstanceByDom(el) || echarts.init(el);
      chart.clear();
      const groups = {};
      rows.forEach((item) => {
        const key = `${item.product_name}-${item.region}`;
        groups[key] ||= [];
        groups[key].push(item);
      });
      const dates = [...new Set(rows.map(item => item.date))].sort();
      chart.setOption({
        tooltip: { trigger: "axis" },
        legend: { type: "scroll", bottom: 0 },
        graphic: rows.length ? [] : [{
          type: "text",
          left: "center",
          top: "middle",
          style: { text: "暂无价格走势数据", fill: "#76837b", fontSize: 14 },
        }],
        grid: { left: 48, right: 18, top: 16, bottom: 56 },
        xAxis: { type: "category", data: dates },
        yAxis: { type: "value", name: "相对价格" },
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
      chart.resize();
      setTimeout(() => chart.resize(), 80);
    },
  },
});

if (window.ElementPlus) {
  app.use(ElementPlus);
}

app.mount("#app");
