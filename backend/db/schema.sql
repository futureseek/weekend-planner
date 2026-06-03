-- POI 基础信息表
CREATE TABLE IF NOT EXISTS poi (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  source_id TEXT,
  name TEXT NOT NULL,
  city TEXT,
  adcode TEXT,
  address TEXT,
  lng REAL NOT NULL,
  lat REAL NOT NULL,
  category TEXT,
  tags TEXT,
  rating REAL,
  avg_cost REAL,
  opening_hours TEXT,
  popularity REAL DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);

-- POI 评价表
CREATE TABLE IF NOT EXISTS poi_review (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  poi_id TEXT,
  source TEXT,
  title TEXT,
  url TEXT,
  content TEXT,
  sentiment REAL,
  keywords TEXT,
  queue_hint TEXT,
  crowd_level INTEGER,
  updated_at TEXT DEFAULT (datetime('now')),
  FOREIGN KEY (poi_id) REFERENCES poi(id)
);

-- 用户画像表
CREATE TABLE IF NOT EXISTS user_profile (
  user_id TEXT PRIMARY KEY,
  liked_categories TEXT,
  disliked_categories TEXT,
  budget_level TEXT,
  pace TEXT,
  transport_preference TEXT,
  queue_tolerance INTEGER DEFAULT 2,
  updated_at TEXT DEFAULT (datetime('now'))
);

-- 用户事件表
CREATE TABLE IF NOT EXISTS user_event (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT,
  event_type TEXT,
  poi_id TEXT,
  itinerary_id TEXT,
  payload TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);

-- 行程方案表
CREATE TABLE IF NOT EXISTS itinerary (
  id TEXT PRIMARY KEY,
  user_id TEXT,
  query TEXT,
  constraints TEXT,
  result_json TEXT,
  score REAL,
  created_at TEXT DEFAULT (datetime('now'))
);

-- 路线缓存表
CREATE TABLE IF NOT EXISTS route_cache (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  origin_poi_id TEXT,
  dest_poi_id TEXT,
  mode TEXT,
  distance_m INTEGER,
  duration_s INTEGER,
  raw_json TEXT,
  updated_at TEXT DEFAULT (datetime('now')),
  UNIQUE(origin_poi_id, dest_poi_id, mode)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_poi_city ON poi(city);
CREATE INDEX IF NOT EXISTS idx_poi_category ON poi(category);
CREATE INDEX IF NOT EXISTS idx_poi_review_poi_id ON poi_review(poi_id);
CREATE INDEX IF NOT EXISTS idx_route_cache_origin ON route_cache(origin_poi_id);
CREATE INDEX IF NOT EXISTS idx_route_cache_dest ON route_cache(dest_poi_id);
