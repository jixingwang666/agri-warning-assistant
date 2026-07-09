"""可插拔搜索引擎适配器层。

采集升级为「关键词 → 搜索引擎 → 结果链接 → 抓正文」的反向爬取。本模块
只负责「关键词 → (真实文章URL, 标题) 列表」，正文抽取仍复用 news_crawler。

内置多个引擎适配器（百度/必应/搜狗/360），均无需 API Key。新增引擎只需继承
_HtmlSearchEngine 配置几个类属性，再在 _ENGINES 里登记即可。

注意：百度对无 Cookie 的直接请求会跳转到「百度安全验证」验证码页，静态抓取
往往拿不到结果；必应/搜狗/360 可正常静态解析。可通过 sources.SEARCH_ENGINE
一行配置切换默认引擎。
"""

from __future__ import annotations

import time
from urllib.parse import parse_qs, urljoin, urlparse

from cleaner import clean_text


_DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)
_MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
)

# 结果里需要过滤掉的域名/路径（搜索引擎自身页、百科/知道/文库/图片等聚合页）。
BAD_RESULT_KEYWORDS = {
    "baike.baidu.com", "zhidao.baidu.com", "wenku.baidu.com", "tieba.baidu.com",
    "map.baidu.com", "image.baidu.com", "v.baidu.com",
    "baike.sogou.com", "baike.so.com", "wenku.so.com", "image.so.com", "so.com/s?",
    "/search?", "/web?", "microsofttranslator", "go.microsoft.com",
}


def _has_chinese(text: str) -> bool:
    return any("一" <= char <= "鿿" for char in text)


class SearchEngine:
    """搜索引擎适配器基类。子类实现 search()。"""

    name = "base"

    def __init__(self, timeout: int = 10, delay: float = 1.0):
        self.timeout = timeout
        self.delay = delay

    def search(self, query: str, limit: int = 5) -> list[tuple[str, str]]:
        """返回 [(真实文章URL, 标题), ...]，最多 limit 条。"""
        raise NotImplementedError


class _HtmlSearchEngine(SearchEngine):
    """基于 HTML 结果页解析的通用搜索引擎适配器。

    子类通过类属性描述差异：搜索URL、查询参数名、结果选择器、跳转标记等。
    """

    search_url = ""
    query_param = "q"
    extra_params: dict = {}
    user_agent = _DESKTOP_UA
    warmup_url = ""  # 若需要先访问首页拿 Cookie，填首页地址
    result_selectors: tuple = ("h3 a",)
    # href 中包含这些标记的视为跳转链接，需要 resolve 到真实地址
    redirect_markers: tuple = ()

    def search(self, query: str, limit: int = 5) -> list[tuple[str, str]]:
        try:
            import requests
            from bs4 import BeautifulSoup
        except ImportError as exc:
            raise RuntimeError("搜索引擎爬虫需要安装 requests 和 beautifulsoup4。") from exc

        session = requests.Session()
        session.headers.update(
            {"User-Agent": self.user_agent, "Accept-Language": "zh-CN,zh;q=0.9"}
        )
        if self.warmup_url:
            try:
                session.get(self.warmup_url, timeout=self.timeout)
            except Exception:
                pass

        params = {self.query_param: query, **self.extra_params}
        response = session.get(self.search_url, params=params, timeout=self.timeout)
        response.raise_for_status()
        response.encoding = response.apparent_encoding

        if self._looks_blocked(response):
            raise RuntimeError(f"{self.name} 返回验证/拦截页面，无法解析结果。")

        soup = BeautifulSoup(response.text, "html.parser")
        candidates = self._extract_candidates(soup)

        results: list[tuple[str, str]] = []
        seen: set[str] = set()
        for link, title in candidates:
            real_url = self._resolve_url(session, link)
            if not real_url or real_url in seen:
                continue
            if not self._is_valid_result(real_url):
                continue
            seen.add(real_url)
            results.append((real_url, title))
            if len(results) >= limit:
                break
            if self.delay:
                time.sleep(self.delay)
        return results

    def _looks_blocked(self, response) -> bool:
        text = response.text
        if len(text) < 3000 and ("安全验证" in text or "验证码" in text):
            return True
        if "wappass.baidu.com" in response.url or "seccaptcha" in text.lower():
            return True
        return False

    def _extract_candidates(self, soup) -> list[tuple[str, str]]:
        candidates: list[tuple[str, str]] = []

        for selector in self.result_selectors:
            for anchor in soup.select(selector):
                self._append_candidate(candidates, anchor)
            if candidates:
                break

        # 兜底：扫描所有中文长文本链接（应对结果页结构变化）。
        if not candidates:
            for anchor in soup.find_all("a"):
                self._append_candidate(candidates, anchor)

        # 按 href 去重，保留顺序。
        deduped: list[tuple[str, str]] = []
        seen: set[str] = set()
        for link, title in candidates:
            if link in seen:
                continue
            seen.add(link)
            deduped.append((link, title))
        return deduped

    def _append_candidate(self, candidates: list[tuple[str, str]], anchor) -> None:
        href = anchor.get("href")
        title = clean_text(anchor.get_text(" "))
        if not href or not title:
            return
        if len(title) < 8 or not _has_chinese(title):
            return
        link = urljoin(self.search_url, href)
        if not link.startswith("http"):
            return
        candidates.append((link, title))

    def _resolve_url(self, session, link: str) -> str | None:
        """跟随跳转链接拿真实文章URL；直链原样返回。"""
        is_redirect = any(marker in link for marker in self.redirect_markers)
        if not is_redirect:
            return link
        try:
            response = session.get(link, timeout=self.timeout, allow_redirects=True)
            final_url = response.url
            if final_url and not self._is_engine_host(final_url):
                return final_url
        except Exception:
            pass
        # 兜底：真实地址可能在查询参数里。
        parsed = parse_qs(urlparse(link).query)
        for key in ("url", "u"):
            if parsed.get(key):
                candidate = parsed[key][0]
                if candidate.startswith("http") and not self._is_engine_host(candidate):
                    return candidate
        return None

    def _is_engine_host(self, url: str) -> bool:
        host = urlparse(url).netloc
        engine_host = urlparse(self.search_url).netloc
        return host.endswith(engine_host.split(".", 1)[-1]) and "link" in url

    def _is_valid_result(self, url: str) -> bool:
        if not url.startswith("http"):
            return False
        if any(keyword in url for keyword in BAD_RESULT_KEYWORDS):
            return False
        return True


class BaiduSearchEngine(_HtmlSearchEngine):
    """百度（无需 API Key）。

    注意：百度对脚本请求普遍返回「百度安全验证」验证码页，静态抓取通常失败，
    这里采用移动端入口 + 首页预热 尽量提高成功率，仍可能被拦截。被拦截时
    抛出异常，由上层记录为该查询的 error 并继续其余查询。
    """

    name = "baidu"
    search_url = "https://m.baidu.com/s"
    query_param = "word"
    user_agent = _MOBILE_UA
    warmup_url = "https://m.baidu.com/"
    result_selectors = ("div.c-result h3 a", "h3 a", "a.c-blocka")
    redirect_markers = ("/from=", "link?url=", "/bd_page_type=")


class BingSearchEngine(_HtmlSearchEngine):
    """必应中文（无需 API Key，直链、结构稳定，推荐用于验证）。"""

    name = "bing"
    search_url = "https://cn.bing.com/search"
    query_param = "q"
    extra_params = {"setlang": "zh-CN", "ensearch": "0"}
    result_selectors = ("li.b_algo h2 a", "ol#b_results h2 a", "h2 a")
    redirect_markers = ()


class SogouSearchEngine(_HtmlSearchEngine):
    """搜狗（无需 API Key）。结果多为 /link?url= 跳转，需 resolve。"""

    name = "sogou"
    search_url = "https://www.sogou.com/web"
    query_param = "query"
    warmup_url = "https://www.sogou.com/"
    result_selectors = ("h3 a", ".vr-title a", ".vrTitle a")
    redirect_markers = ("/link?url=",)


class So360SearchEngine(_HtmlSearchEngine):
    """360 搜索（无需 API Key）。结果为 so.com/link?m= 跳转，需 resolve。"""

    name = "so360"
    search_url = "https://www.so.com/s"
    query_param = "q"
    warmup_url = "https://www.so.com/"
    result_selectors = ("li.res-list h3 a", "h3.res-title a", "h3 a")
    redirect_markers = ("so.com/link?m=", "/link?m=")


_ENGINES = {
    "baidu": BaiduSearchEngine,
    "bing": BingSearchEngine,
    "sogou": SogouSearchEngine,
    "so360": So360SearchEngine,
}


class MultiSearchEngine(SearchEngine):
    """按顺序尝试多个引擎，返回第一个有结果的。

    应对搜索引擎反爬：某引擎被验证码/限流拦截(抛异常或返回空)时，自动切换到
    下一个引擎，提升整体成功率。
    """

    name = "multi"

    def __init__(self, engines: list[SearchEngine]):
        self.engines = engines

    def search(self, query: str, limit: int = 5) -> list[tuple[str, str]]:
        last_error: Exception | None = None
        for engine in self.engines:
            try:
                results = engine.search(query, limit=limit)
                if results:
                    return results
            except Exception as exc:  # 该引擎被拦截，尝试下一个。
                last_error = exc
                continue
        if last_error is not None:
            raise last_error
        return []


def get_engine(name: str = "baidu", timeout: int = 10, delay: float = 1.0) -> SearchEngine:
    """按名称返回单个搜索引擎适配器实例。"""
    engine_cls = _ENGINES.get((name or "").lower())
    if engine_cls is None:
        raise ValueError(f"暂不支持的搜索引擎: {name}，可选: {sorted(_ENGINES)}")
    return engine_cls(timeout=timeout, delay=delay)


def build_engine_chain(
    primary: str = "baidu",
    fallbacks: list[str] | None = None,
    timeout: int = 10,
    delay: float = 1.0,
) -> SearchEngine:
    """构建「主引擎 + 备用引擎」的容错链。

    百度常被验证码拦截，配置 fallbacks(如 ["bing","sogou","so360"]) 后，主引擎
    失败会自动切换，保证反向爬取尽量拿到结果。
    """
    names: list[str] = [primary]
    for name in fallbacks or []:
        if name and name.lower() not in [n.lower() for n in names]:
            names.append(name)
    engines = [get_engine(n, timeout=timeout, delay=delay) for n in names]
    return MultiSearchEngine(engines)
