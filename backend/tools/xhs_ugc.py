import json
import re
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests
from langchain_core.tools import tool

from .tavily import search_reviews


XHS_DOMAINS = {"xiaohongshu.com", "www.xiaohongshu.com", "xhslink.com"}
BLOCK_HINTS = ["验证码", "登录", "安全验证", "访问异常", "滑块", "captcha", "verify"]


def _is_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_xhs_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host == domain or host.endswith("." + domain) for domain in XHS_DOMAINS)


def _parse_search_items(raw: str) -> list[dict]:
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict) and data.get("error"):
        return []
    return data if isinstance(data, list) else data.get("results", [])


@tool
def search_xhs_public_notes(query: str, limit: int = 5) -> str:
    """搜索公开索引里的小红书笔记摘要。

    只使用搜索引擎可见摘要，不登录、不绕过验证码、不批量抓取页面。
    适合给路线规划补充“种草/避雷/排队/拍照点”等 UGC 信号。
    """
    limit = max(1, min(int(limit or 5), 10))
    search_queries = [
        f"site:xiaohongshu.com {query} 小红书 攻略 推荐 排队 避雷",
        f"{query} 小红书 攻略 推荐 排队 避雷",
        f"{query} 种草 避雷 探店 推荐",
    ]

    items = []
    for search_query in search_queries:
        raw = search_reviews.invoke({"query": search_query})
        items = _parse_search_items(raw)
        if items:
            break

    results = []
    for item in items:
        url = item.get("url", "")
        title = item.get("title", "")
        content = item.get("content", "")
        if _is_xhs_url(url) or "小红书" in title or "小红书" in content:
            results.append({
                "title": title,
                "url": url,
                "content": content[:300],
                "source": "xhs_search",
            })
        if len(results) >= limit:
            break

    if not results and items:
        for item in items[:limit]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", "")[:300],
                "source": "public_search",
            })

    return json.dumps(results, ensure_ascii=False)


class _VisibleTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden_depth = 0
        self.parts: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden_depth += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self.hidden_depth:
            self.hidden_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        text = re.sub(r"\s+", " ", data or "").strip()
        if not text:
            return
        if self._in_title:
            self.title += text
        elif self.hidden_depth == 0:
            self.parts.append(text)

    def visible_text(self) -> str:
        return "\n".join(self.parts)


@tool
def read_public_webpage(url: str, max_chars: int = 4000) -> str:
    """读取公开网页的可见文本。

    该工具只读取无需登录、无需验证码的公开页面；遇到登录墙或验证页会停止并返回错误。
    它不是反爬绕过工具，不使用代理、指纹伪装或验证码处理。
    """
    if not _is_http_url(url):
        return json.dumps({"error": "只支持 http/https URL"}, ensure_ascii=False)

    max_chars = max(500, min(int(max_chars or 4000), 8000))

    browser_result = _read_with_optional_browser(url, max_chars)
    if browser_result:
        return browser_result

    # 先用轻量 HTTP 读取；公开文章页、搜索结果页和普通网页通常足够。
    try:
        res = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 route-planner-public-reader"},
            timeout=10,
        )
        html = res.text or ""
    except Exception as exc:
        return json.dumps({"error": f"读取失败: {type(exc).__name__}"}, ensure_ascii=False)

    if res.status_code >= 400:
        return json.dumps({"error": f"HTTP {res.status_code}"}, ensure_ascii=False)

    if any(hint.lower() in html.lower() for hint in BLOCK_HINTS):
        return json.dumps({"error": "页面需要登录或验证，已停止读取"}, ensure_ascii=False)

    parser = _VisibleTextParser()
    parser.feed(html)
    text = parser.visible_text()

    return json.dumps({
        "url": url,
        "title": parser.title[:120],
        "content": text[:max_chars],
        "source": "public_webpage",
    }, ensure_ascii=False)


def _read_with_optional_browser(url: str, max_chars: int) -> str | None:
    """如果本机安装了 Playwright，就用真实浏览器渲染公开页面。"""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(1200)
            title = page.title()
            text = page.locator("body").inner_text(timeout=5000)
            browser.close()
    except Exception:
        return None

    if any(hint.lower() in text.lower() for hint in BLOCK_HINTS):
        return json.dumps({"error": "页面需要登录或验证，已停止读取"}, ensure_ascii=False)

    return json.dumps({
        "url": url,
        "title": title[:120],
        "content": text[:max_chars],
        "source": "public_browser",
    }, ensure_ascii=False)


def get_xhs_tools():
    return [search_xhs_public_notes, read_public_webpage]
