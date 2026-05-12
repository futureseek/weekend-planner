import json
from tools.tavily import search_reviews
from db.database import execute_query, execute_one, execute_write

# 关键词分类
POSITIVE_KEYWORDS = ["推荐", "好吃", "好看", "出片", "安静", "性价比", "必去", "打卡", "环境好", "服务好"]
NEGATIVE_KEYWORDS = ["排队", "拥挤", "难吃", "服务差", "贵", "踩雷", "避雷", "失望"]
QUEUE_KEYWORDS = ["排队", "等位", "人多", "火爆", "网红"]


def get_review_summary(poi_id: str) -> dict | None:
    """从本地获取 POI 的评价摘要"""
    return execute_one(
        "SELECT * FROM poi_review WHERE poi_id = ? ORDER BY updated_at DESC LIMIT 1",
        (poi_id,)
    )


def extract_keywords(content: str) -> list[str]:
    """从评价内容中提取关键词"""
    found = []
    for kw in POSITIVE_KEYWORDS + NEGATIVE_KEYWORDS + QUEUE_KEYWORDS:
        if kw in content:
            found.append(kw)
    return list(set(found))


def analyze_sentiment(content: str) -> float:
    """简单情感分析，返回 -1 到 1 的分数"""
    pos_count = sum(1 for kw in POSITIVE_KEYWORDS if kw in content)
    neg_count = sum(1 for kw in NEGATIVE_KEYWORDS if kw in content)
    total = pos_count + neg_count
    if total == 0:
        return 0.0
    return (pos_count - neg_count) / total


def detect_queue_risk(content: str) -> str:
    """检测排队风险"""
    queue_count = sum(1 for kw in QUEUE_KEYWORDS if kw in content)
    if queue_count >= 2:
        return "high"
    elif queue_count == 1:
        return "medium"
    return "low"


def search_and_save_reviews(poi_name: str, city: str, poi_id: str) -> dict | None:
    """搜索评价并保存到数据库"""
    query = f"{city} {poi_name} 推荐 排队 评价"
    result = search_reviews.invoke({"query": query})

    try:
        data = json.loads(result) if isinstance(result, str) else result
    except json.JSONDecodeError:
        return None

    if "error" in data:
        return None

    items = data if isinstance(data, list) else data.get("results", [])
    if not items:
        return None

    # 合并所有搜索结果
    combined_content = " ".join(item.get("content", "")[:100] for item in items[:3])
    title = items[0].get("title", "")
    url = items[0].get("url", "")

    keywords = extract_keywords(combined_content)
    sentiment = analyze_sentiment(combined_content)
    queue_hint = detect_queue_risk(combined_content)

    # 保存到数据库
    execute_write("""
        INSERT INTO poi_review (poi_id, source, title, url, content, sentiment, keywords, queue_hint, crowd_level)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        poi_id,
        "tavily",
        title,
        url,
        combined_content[:500],
        sentiment,
        json.dumps(keywords, ensure_ascii=False),
        queue_hint,
        2 if queue_hint == "medium" else 3 if queue_hint == "high" else 1,
    ))

    return {
        "poi_id": poi_id,
        "title": title,
        "content": combined_content[:200],
        "keywords": keywords,
        "sentiment": sentiment,
        "queue_hint": queue_hint,
    }


def enrich_reviews(pois: list[dict]) -> list[dict]:
    """为 POI 列表补全评价信息"""
    enriched = []
    for poi in pois:
        poi_id = poi["id"]

        # 先查本地缓存
        review = get_review_summary(poi_id)
        if review:
            poi["review"] = {
                "keywords": json.loads(review["keywords"]) if review["keywords"] else [],
                "sentiment": review["sentiment"],
                "queue_hint": review["queue_hint"],
                "content": review["content"],
            }
        else:
            # 从 Tavily 搜索
            result = search_and_save_reviews(poi["name"], poi.get("city", ""), poi_id)
            if result:
                poi["review"] = result
            else:
                poi["review"] = {
                    "keywords": [],
                    "sentiment": 0,
                    "queue_hint": "unknown",
                    "content": "",
                }

        enriched.append(poi)

    return enriched
