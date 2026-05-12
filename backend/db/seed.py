import json
import uuid
from .database import execute_many, execute_query

# 杭州西湖/湖滨区域样例 POI 数据
HANGZHOU_POIS = [
    # 咖啡店
    {
        "name": "福叁咖啡(西湖店)",
        "city": "杭州",
        "address": "杭州市上城区湖滨路23号",
        "lng": 120.1612,
        "lat": 30.2491,
        "category": "咖啡",
        "tags": ["咖啡", "西湖", "安静", "适合拍照"],
        "rating": 4.6,
        "avg_cost": 45,
    },
    {
        "name": "%Arabica(湖滨银泰店)",
        "city": "杭州",
        "address": "杭州市上城区东坡路7号湖滨银泰in77A区",
        "lng": 120.1634,
        "lat": 30.2502,
        "category": "咖啡",
        "tags": ["咖啡", "网红", "排队", "拍照"],
        "rating": 4.4,
        "avg_cost": 40,
    },
    {
        "name": "星巴克臻选(湖滨店)",
        "city": "杭州",
        "address": "杭州市上城区湖滨路51号",
        "lng": 120.1618,
        "lat": 30.2485,
        "category": "咖啡",
        "tags": ["咖啡", "连锁", "稳定"],
        "rating": 4.3,
        "avg_cost": 38,
    },
    # 餐厅
    {
        "name": "楼外楼(孤山店)",
        "city": "杭州",
        "address": "杭州市西湖区孤山路30号",
        "lng": 120.1487,
        "lat": 30.2512,
        "category": "餐厅",
        "tags": ["杭帮菜", "老字号", "西湖醋鱼", "排队"],
        "rating": 4.2,
        "avg_cost": 120,
    },
    {
        "name": "知味观·味庄(杨公堤店)",
        "city": "杭州",
        "address": "杭州市西湖区杨公堤10-12号",
        "lng": 120.1398,
        "lat": 30.2456,
        "category": "餐厅",
        "tags": ["杭帮菜", "环境好", "适合约会", "景观位"],
        "rating": 4.5,
        "avg_cost": 150,
    },
    {
        "name": "外婆家(湖滨店)",
        "city": "杭州",
        "address": "杭州市上城区湖滨路53号",
        "lng": 120.1621,
        "lat": 30.2488,
        "category": "餐厅",
        "tags": ["杭帮菜", "性价比高", "排队"],
        "rating": 4.1,
        "avg_cost": 65,
    },
    {
        "name": "新白鹿(龙翔桥店)",
        "city": "杭州",
        "address": "杭州市上城区东坡路9号",
        "lng": 120.1630,
        "lat": 30.2498,
        "category": "餐厅",
        "tags": ["杭帮菜", "平价", "本地人推荐"],
        "rating": 4.3,
        "avg_cost": 55,
    },
    # 景点
    {
        "name": "断桥残雪",
        "city": "杭州",
        "address": "杭州市西湖区北山街",
        "lng": 120.1545,
        "lat": 30.2592,
        "category": "景点",
        "tags": ["西湖十景", "免费", "拍照", "人多"],
        "rating": 4.7,
        "avg_cost": 0,
    },
    {
        "name": "雷峰塔",
        "city": "杭州",
        "address": "杭州市西湖区南山路15号",
        "lng": 120.1498,
        "lat": 30.2389,
        "category": "景点",
        "tags": ["西湖十景", "登塔", "俯瞰西湖"],
        "rating": 4.4,
        "avg_cost": 40,
    },
    {
        "name": "三潭印月",
        "city": "杭州",
        "address": "杭州市西湖区西湖中心",
        "lng": 120.1456,
        "lat": 30.2445,
        "category": "景点",
        "tags": ["西湖十景", "坐船", "必去"],
        "rating": 4.6,
        "avg_cost": 55,
    },
    {
        "name": "苏堤",
        "city": "杭州",
        "address": "杭州市西湖区",
        "lng": 120.1423,
        "lat": 30.2478,
        "category": "景点",
        "tags": ["西湖十景", "散步", "免费", "浪漫"],
        "rating": 4.8,
        "avg_cost": 0,
    },
    {
        "name": "花港观鱼",
        "city": "杭州",
        "address": "杭州市西湖区杨公堤",
        "lng": 120.1389,
        "lat": 30.2412,
        "category": "景点",
        "tags": ["西湖十景", "免费", "亲子", "喂鱼"],
        "rating": 4.5,
        "avg_cost": 0,
    },
    # 展览/博物馆
    {
        "name": "浙江省博物馆(孤山馆区)",
        "city": "杭州",
        "address": "杭州市西湖区孤山路25号",
        "lng": 120.1482,
        "lat": 30.2518,
        "category": "展览",
        "tags": ["博物馆", "免费", "看展", "文化"],
        "rating": 4.5,
        "avg_cost": 0,
    },
    {
        "name": "中国美术学院美术馆",
        "city": "杭州",
        "address": "杭州市上城区南山路218号",
        "lng": 120.1545,
        "lat": 30.2412,
        "category": "展览",
        "tags": ["美术馆", "看展", "拍照", "艺术"],
        "rating": 4.4,
        "avg_cost": 20,
    },
    {
        "name": "西湖博物馆",
        "city": "杭州",
        "address": "杭州市上城区南山路89号",
        "lng": 120.1567,
        "lat": 30.2435,
        "category": "展览",
        "tags": ["博物馆", "免费", "了解西湖"],
        "rating": 4.3,
        "avg_cost": 0,
    },
    # 甜品/小吃
    {
        "name": "知味观(总店)",
        "city": "杭州",
        "address": "杭州市上城区仁和路83号",
        "lng": 120.1645,
        "lat": 30.2512,
        "category": "甜品",
        "tags": ["小吃", "老字号", "猫耳朵", "片儿川"],
        "rating": 4.2,
        "avg_cost": 30,
    },
    {
        "name": "弄堂里(湖滨店)",
        "city": "杭州",
        "address": "杭州市上城区东坡路",
        "lng": 120.1632,
        "lat": 30.2505,
        "category": "甜品",
        "tags": ["甜品", "下午茶", "环境好"],
        "rating": 4.3,
        "avg_cost": 50,
    },
    # 公园/休闲
    {
        "name": "太子湾公园",
        "city": "杭州",
        "address": "杭州市西湖区南山路1-1号",
        "lng": 120.1412,
        "lat": 30.2389,
        "category": "公园",
        "tags": ["公园", "免费", "赏花", "野餐"],
        "rating": 4.6,
        "avg_cost": 0,
    },
    {
        "name": "柳浪闻莺",
        "city": "杭州",
        "address": "杭州市上城区南山路",
        "lng": 120.1578,
        "lat": 30.2401,
        "category": "公园",
        "tags": ["西湖十景", "公园", "免费", "散步"],
        "rating": 4.5,
        "avg_cost": 0,
    },
    # 购物
    {
        "name": "湖滨银泰in77",
        "city": "杭州",
        "address": "杭州市上城区东坡路7号",
        "lng": 120.1635,
        "lat": 30.2505,
        "category": "购物",
        "tags": ["商场", "购物", "吃饭", "逛街"],
        "rating": 4.4,
        "avg_cost": 100,
    },
]


def seed_pois():
    """导入样例 POI 数据"""
    existing = execute_query("SELECT COUNT(*) as cnt FROM poi")
    if existing and existing[0]["cnt"] > 0:
        print(f"POI 表已有 {existing[0]['cnt']} 条数据，跳过导入")
        return

    sql = """
    INSERT INTO poi (id, source, source_id, name, city, adcode, address, lng, lat, category, tags, rating, avg_cost)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    params_list = []
    for poi in HANGZHOU_POIS:
        poi_id = f"poi_{uuid.uuid4().hex[:8]}"
        params_list.append((
            poi_id,
            "manual",
            None,
            poi["name"],
            poi["city"],
            "330100",  # 杭州 adcode
            poi["address"],
            poi["lng"],
            poi["lat"],
            poi["category"],
            json.dumps(poi["tags"], ensure_ascii=False),
            poi["rating"],
            poi["avg_cost"],
        ))

    execute_many(sql, params_list)
    print(f"成功导入 {len(params_list)} 条 POI 数据")


if __name__ == "__main__":
    from database import init_db
    init_db()
    seed_pois()
