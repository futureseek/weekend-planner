import json
import os
from langchain_core.tools import tool
from langchain_tavily import TavilySearch

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config", "api_config.json")

with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
    _config = json.load(f)

TAVILY_API_KEY = _config.get("tavily_key", "")


@tool
def search_reviews(query: str) -> str:
    """搜索引擎搜索地点的用户评价和推荐。

    用于查找某个地点或活动的真实用户评价、探店体验。
    搜索结果来自大众点评、抖音、小红书等平台。

    Args:
        query: 搜索关键词，如"杭州福叁咖啡 探店评价"、"浙江美术馆 周末看展推荐"

    Returns:
        搜索结果摘要，包含标题、链接、内容描述
    """
    try:
        search = TavilySearch(tavily_api_key=TAVILY_API_KEY)
        results = search.run(query)

        if not results or not isinstance(results, dict):
            return json.dumps({"error": "未找到相关结果"}, ensure_ascii=False)

        items = []
        for r in results.get("results", [])[:5]:
            items.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", "")[:200],
            })

        return json.dumps(items, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
