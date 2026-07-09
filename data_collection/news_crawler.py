from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin
import warnings

from cleaner import clean_text


BAD_TITLE_KEYWORDS = {
    "English",
    "邮箱",
    "举报中心",
    "中国农业农村信息网",
    "友情链接",
    "网站地图",
    "导报",
    "信用合作报",
}

BAD_URL_KEYWORDS = {
    "mail.",
    "english.",
    "12377.cn",
}


@dataclass
class CrawlResult:
    items: list[dict]
    errors: list[str]


class NewsCrawler:
    """A lightweight crawler for public agriculture news pages.

    The parser is intentionally conservative because government/news pages
    often have different structures. It extracts common article links from a
    list page, then tries several common selectors for article metadata.
    """

    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    def crawl_sources(self, sources: Iterable[dict], limit_per_source: int = 10) -> CrawlResult:
        items: list[dict] = []
        errors: list[str] = []
        source_list = list(sources)
        max_workers = min(max(len(source_list), 1), 4)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.crawl_source, source, limit_per_source): source
                for source in source_list
            }
            for future in as_completed(futures):
                source = futures[future]
                try:
                    items.extend(future.result())
                except Exception as exc:  # Keep one source failure from stopping the batch.
                    errors.append(f"{source.get('name', 'unknown')}: {exc}")
        return CrawlResult(items=items, errors=errors)

    def crawl_source(self, source: dict, limit: int = 10) -> list[dict]:
        try:
            import requests
            from bs4 import BeautifulSoup
        except ImportError as exc:
            raise RuntimeError("网页爬虫需要安装 requests 和 beautifulsoup4。") from exc

        headers = {"User-Agent": "Mozilla/5.0 AgriWarningBot/1.0"}
        verify_ssl = source.get("verify_ssl", True)
        if not verify_ssl:
            warnings.filterwarnings("ignore", message="Unverified HTTPS request")
        response = requests.get(source["list_url"], headers=headers, timeout=self.timeout, verify=verify_ssl)
        response.raise_for_status()
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, "html.parser")

        links = self._extract_links(soup, source, max(limit * 2, limit))
        items = []
        for url, title in links:
            try:
                item = self.fetch_detail(url, source)
                if not item["title"]:
                    item["title"] = title
                items.append(item)
                if len(items) >= limit:
                    break
            except Exception:
                continue
        return items

    def crawl_by_queries(
        self,
        queries: list[dict],
        engine,
        limit_per_query: int = 5,
    ) -> CrawlResult:
        """关键词反向爬取：关键词 → 搜索引擎 → 真实文章URL → 抓正文。

        queries: [{"query": str, "region": str, "risk_type": str}, ...]
            由 keyword_query.build_search_queries / parse_manual_keywords 生成。
        engine: search_engines.SearchEngine 实例（默认百度）。
        复用 fetch_detail 抓正文，按真实 URL 去重，单个 query 失败不中断整批。
        """
        items: list[dict] = []
        errors: list[str] = []
        seen_urls: set[str] = set()

        for spec in queries:
            query = spec.get("query", "")
            region = spec.get("region", "")
            if not query:
                continue
            try:
                results = engine.search(query, limit=limit_per_query)
            except Exception as exc:  # 单个查询失败不影响其余查询。
                errors.append(f"{query}: {exc}")
                continue

            for url, title in results:
                if url in seen_urls:
                    continue
                if not self._is_probable_news_link(title, url):
                    continue
                seen_urls.add(url)
                try:
                    source = {"name": _domain_of(url), "region": region, "category": ""}
                    item = self.fetch_detail(url, source)
                    if not item["title"]:
                        item["title"] = title
                    if not item.get("region"):
                        item["region"] = region
                    items.append(item)
                except Exception:
                    continue
        return CrawlResult(items=items, errors=errors)


    def fetch_detail(self, url: str, source: dict) -> dict:
        import requests
        from bs4 import BeautifulSoup

        headers = {"User-Agent": "Mozilla/5.0 AgriWarningBot/1.0"}
        verify_ssl = source.get("verify_ssl", True)
        if not verify_ssl:
            warnings.filterwarnings("ignore", message="Unverified HTTPS request")
        response = requests.get(url, headers=headers, timeout=self.timeout, verify=verify_ssl)
        response.raise_for_status()
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, "html.parser")

        title = self._pick_text(soup, ["h1", ".title", "#title"])
        content = self._pick_article_text(soup)
        publish_time = self._pick_text(soup, [".time", ".date", ".source", ".info"])

        return {
            "title": clean_text(title),
            "content": clean_text(content),
            "source": source.get("name", ""),
            "publish_time": clean_text(publish_time),
            "url": url,
            "region": source.get("region", ""),
            "category": source.get("category", ""),
        }

    def _extract_links(self, soup, source: dict, limit: int) -> list[tuple[str, str]]:
        links = []
        for anchor in soup.find_all("a"):
            title = clean_text(anchor.get_text(" "))
            href = anchor.get("href")
            url = urljoin(source.get("base_url") or source["list_url"], href)
            if self._is_probable_news_link(title, url):
                links.append((url, title))
            if len(links) >= limit:
                break
        return links

    def _is_probable_news_link(self, title: str, url: str) -> bool:
        if not title or not url.startswith("http"):
            return False
        if len(title) < 8:
            return False
        if not re_search_chinese(title):
            return False
        if any(keyword in title for keyword in BAD_TITLE_KEYWORDS):
            return False
        if any(keyword in url for keyword in BAD_URL_KEYWORDS):
            return False
        return True

    def _pick_text(self, soup, selectors: list[str]) -> str:
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                return element.get_text(" ")
        return ""

    def _pick_article_text(self, soup) -> str:
        selectors = ["article", ".article", ".content", "#content", ".TRS_Editor", ".main"]
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                text = element.get_text(" ")
                if len(clean_text(text)) > 50:
                    return text
        paragraphs = [p.get_text(" ") for p in soup.find_all("p")]
        return " ".join(paragraphs)


def re_search_chinese(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _domain_of(url: str) -> str:
    """\u4ece URL \u53d6\u57df\u540d\u4f5c\u4e3a\u6765\u6e90\u540d\uff08\u641c\u7d22\u91c7\u96c6\u65f6\u6ca1\u6709\u9884\u8bbe source \u540d\uff09\u3002"""
    from urllib.parse import urlparse

    try:
        return urlparse(url).netloc or "\u641c\u7d22\u91c7\u96c6"
    except Exception:
        return "\u641c\u7d22\u91c7\u96c6"
