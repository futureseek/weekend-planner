"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { apiPost } from "@/lib/api";

export interface ItineraryBlock {
  id: string;
  type: string;
  icon: string;
  name: string;
  duration: number;
  price: number;
  unit_price?: number;
  recommendation?: string;
  reason?: string;
  address: string;
  rating?: number;
  tags?: string[];
  category?: string;
  lng?: number | string;
  lat?: number | string;
  day_index?: number;
  start_time?: string;
  end_time?: string;
  time_note?: string;
  is_auxiliary?: boolean;
  is_start?: boolean;
}

export interface Connection {
  from: string;
  to: string;
  distance: string;
  time: string;
  mode?: string;
  day_index?: number;
  from_name?: string;
  to_name?: string;
  from_lng?: number | string;
  from_lat?: number | string;
  to_lng?: number | string;
  to_lat?: number | string;
  city?: string;
  distance_m?: number;
  duration_minutes?: number;
  route_path?: Array<{ lng: number | string; lat: number | string }>;
  transit_detail?: {
    summary?: string;
    duration?: string;
    walking_distance?: string;
    cost?: string;
    segments?: string[];
  };
}

export interface ItineraryDay {
  day_index: number;
  title: string;
  date_label?: string;
  start_time: string;
  end_time: string;
  total_duration: number;
  total_price: number;
  blocks: ItineraryBlock[];
  connections: Connection[];
}

export interface EventSuggestion {
  title: string;
  summary?: string;
  url?: string;
  tags?: string[];
  source?: string;
}

export interface UpgradeSuggestion {
  title: string;
  summary?: string;
  summary_en?: string;
  estimated_cost?: number;
  category?: string;
  tags?: string[];
  reason?: string;
  source?: string;
}

export interface Itinerary {
  blocks: ItineraryBlock[];
  connections: Connection[];
  days?: ItineraryDay[];
  total_duration: number;
  total_price: number;
  plan_name?: string;
  style?: string;
  highlights?: string[];
  score?: number;
  total_distance?: number;
  alternatives?: Itinerary[];
  time_plan?: {
    daily_start_time?: string;
    daily_end_time?: string;
    trip_days?: number;
    note?: string;
  };
  event_suggestions?: EventSuggestion[];
  upgrade_suggestions?: UpgradeSuggestion[];
  map_pois?: ItineraryBlock[];
  start_transfer?: Connection;
  guide_signals?: {
    strategy?: string[];
    snippets?: string[];
    positive_keywords?: string[];
    avoid_keywords?: string[];
  };
}

type Language = "zh" | "en";

const AMAP_JS_KEY = process.env.NEXT_PUBLIC_AMAP_JS_KEY || "";
const AMAP_SECURITY_JS_CODE = process.env.NEXT_PUBLIC_AMAP_SECURITY_JS_CODE || "";

const CANVAS_TEXT = {
  zh: {
    lab: "Roam Route Lab",
    routePlan: "路线方案",
    defaultTimeNote: "按可用时间拆分行程",
    totalDuration: "总时长",
    totalCost: "预计花费",
    transferDistance: "转场距离",
    dayUnit: "天",
    stops: "站",
    segments: "段转场",
    mapView: "Map View",
    route: "路线",
    nearbyPoi: "周边 POI",
    dragHint: "区域示意 · 点击地点",
    zoom: "缩放",
    reset: "复位",
    startAccess: "起点接入",
    checklist: "Checklist",
    dayChecklist: "路线安排",
    timeOrder: "按时间顺序 · 可点击定位",
    quickAdjust: "快速调整",
    adjusting: "调整中...",
    nearby: "周边 POI",
    minute: "分钟",
    rating: "评分",
    suggestions: "建议",
    suggestionHint: "愿意追加部分预算时可考虑",
    estimated: "预计",
    actions: {
      less_walking: "少走路",
      lower_budget: "性价比",
      less_queue: "少排队",
      replace_poi: "换餐厅",
    },
  },
  en: {
    lab: "Roam Route Lab",
    routePlan: "Route plan",
    defaultTimeNote: "Split by available time windows",
    totalDuration: "Duration",
    totalCost: "Cost",
    transferDistance: "Transfer distance",
    dayUnit: "days",
    stops: "stops",
    segments: "transfers",
    mapView: "Map View",
    route: "Route",
    nearbyPoi: "Nearby POI",
    dragHint: "Area map · click marker",
    zoom: "Zoom",
    reset: "Reset",
    startAccess: "Start access",
    checklist: "Checklist",
    dayChecklist: "Route schedule",
    timeOrder: "Time order · click to locate",
    quickAdjust: "Quick adjust",
    adjusting: "Adjusting...",
    nearby: "Nearby POI",
    minute: "min",
    rating: "Rating",
    suggestions: "Suggestions",
    suggestionHint: "Optional upgrades if you can stretch the budget",
    estimated: "est.",
    actions: {
      less_walking: "Less walking",
      lower_budget: "Better value",
      less_queue: "Fewer queues",
      replace_poi: "Swap restaurant",
    },
  },
};

const TYPE_STYLES: Record<string, { bg: string; text: string; border: string; stroke: string; fill: string }> = {
  start: { bg: "bg-blue-50", text: "text-blue-800", border: "border-blue-200", stroke: "#2563eb", fill: "#eff6ff" },
  cafe: { bg: "bg-amber-50", text: "text-amber-800", border: "border-amber-200", stroke: "#f59e0b", fill: "#fffbeb" },
  food: { bg: "bg-orange-50", text: "text-orange-800", border: "border-orange-200", stroke: "#fb923c", fill: "#fff7ed" },
  restaurant: { bg: "bg-orange-50", text: "text-orange-800", border: "border-orange-200", stroke: "#fb923c", fill: "#fff7ed" },
  scenic: { bg: "bg-teal-50", text: "text-teal-800", border: "border-teal-200", stroke: "#14b8a6", fill: "#f0fdfa" },
  exhibition: { bg: "bg-sky-50", text: "text-sky-800", border: "border-sky-200", stroke: "#38bdf8", fill: "#f0f9ff" },
  park: { bg: "bg-emerald-50", text: "text-emerald-800", border: "border-emerald-200", stroke: "#10b981", fill: "#ecfdf5" },
  shopping: { bg: "bg-rose-50", text: "text-rose-800", border: "border-rose-200", stroke: "#fb7185", fill: "#fff1f2" },
  entertainment: { bg: "bg-violet-50", text: "text-violet-800", border: "border-violet-200", stroke: "#8b5cf6", fill: "#f5f3ff" },
};

const DEFAULT_STYLE = { bg: "bg-slate-50", text: "text-slate-700", border: "border-slate-200", stroke: "#64748b", fill: "#f8fafc" };

function getStyle(type?: string) {
  return type ? TYPE_STYLES[type.toLowerCase()] || DEFAULT_STYLE : DEFAULT_STYLE;
}

function formatDistance(distance?: number, language: Language = "zh") {
  if (!distance) return language === "en" ? "Unknown" : "未知";
  return distance < 1000 ? `${distance}m` : `${(distance / 1000).toFixed(1)}km`;
}

function parseDurationMinutes(time?: string, fallback?: number | null) {
  if (typeof fallback === "number" && Number.isFinite(fallback) && fallback >= 0) return Math.round(fallback);
  const text = String(time || "");
  const zhHour = text.match(/(\d+)\s*小时(?:(\d+)\s*分钟)?/);
  if (zhHour) return Number(zhHour[1]) * 60 + Number(zhHour[2] || 0);
  const zhMin = text.match(/(\d+)\s*分钟/);
  if (zhMin) return Number(zhMin[1]);
  const enHour = text.match(/(\d+)\s*(?:h|hour|hours)(?:\s*(\d+)\s*(?:m|min|mins|minute|minutes))?/i);
  if (enHour) return Number(enHour[1]) * 60 + Number(enHour[2] || 0);
  const enMin = text.match(/(\d+)\s*(?:m|min|mins|minute|minutes)/i);
  if (enMin) return Number(enMin[1]);
  return null;
}

function formatDurationLabel(time: string | undefined, language: Language, fallback?: number | null) {
  const minutes = parseDurationMinutes(time, fallback);
  if (minutes === null) return time || (language === "en" ? "unknown" : "未知");
  if (language === "en") {
    if (minutes < 60) return `${minutes}min`;
    const rest = minutes % 60;
    return rest ? `${Math.floor(minutes / 60)}h ${rest}min` : `${Math.floor(minutes / 60)}h`;
  }
  if (minutes < 60) return `${minutes}分钟`;
  const rest = minutes % 60;
  return rest ? `${Math.floor(minutes / 60)}小时${rest}分钟` : `${Math.floor(minutes / 60)}小时`;
}

function parseDistanceMeters(distance?: string, fallback?: number | null) {
  if (typeof fallback === "number" && Number.isFinite(fallback) && fallback >= 0) return Math.round(fallback);
  const text = String(distance || "").trim();
  const km = text.match(/([\d.]+)\s*km/i);
  if (km) return Math.round(Number(km[1]) * 1000);
  const meter = text.match(/([\d.]+)\s*m/i);
  if (meter) return Math.round(Number(meter[1]));
  return null;
}

function formatDistanceLabel(distance: string | undefined, language: Language, fallback?: number | null) {
  const meters = parseDistanceMeters(distance, fallback);
  if (meters === null) return distance || (language === "en" ? "unknown" : "未知");
  if (language === "en") return meters < 1000 ? `${meters}m` : `${(meters / 1000).toFixed(1)}km`;
  return meters < 1000 ? `${meters}m` : `${(meters / 1000).toFixed(1)}km`;
}

const PLAN_NAME_EN: Record<string, string> = {
  "综合推荐": "Best Overall",
  "少走路": "Less Walking",
  "吃好玩好": "Food & Fun",
  "省钱轻量": "Value Pick",
  "多日综合": "Multi-day Balanced",
  "预算充分": "Richer Budget Use",
  "少折返": "Compact Route",
  "轻松留白": "Relaxed Pace",
  "兴趣强化": "Interest First",
  "休闲放松": "Relaxed Comfort",
};

const MODE_EN: Record<string, string> = {
  "步行": "Walking",
  "骑行": "Cycling",
  "驾车": "Driving",
  "公共交通": "Transit",
};
const CATEGORY_EN: Record<string, string> = {
  "起点": "Start",
  "咖啡": "Cafe",
  "餐厅": "Restaurant",
  "甜品": "Dessert",
  "景点": "Scenic spot",
  "展览": "Exhibition",
  "公园": "Park",
  "购物": "Shopping",
  "夜景": "Night view",
  "娱乐": "Entertainment",
  "商圈": "Commercial area",
  "酒家": "Cantonese restaurant",
  "茶楼": "Tea restaurant",
  "早茶": "Morning tea",
  "电竞馆": "Esports venue",
  "密室": "Escape room",
};
const TAG_EN: Record<string, string> = {
  "广州": "Guangzhou",
  "天河区": "Tianhe",
  "番禺区": "Panyu",
  "海珠区": "Haizhu",
  "越秀区": "Yuexiu",
  "荔湾区": "Liwan",
  "白云区": "Baiyun",
  "黄埔区": "Huangpu",
  "增城区": "Zengcheng",
  "花都区": "Huadu",
  "南沙区": "Nansha",
  "从化区": "Conghua",
  "咖啡馆": "Cafe",
  "餐厅": "Restaurant",
  "甜品": "Dessert",
  "景点": "Scenic spot",
  "公园": "Park",
  "商圈": "Commercial area",
  "购物": "Shopping",
  "夜景": "Night view",
  "娱乐": "Entertainment",
  "电竞馆": "Esports venue",
  "Livehouse": "Livehouse",
  "酒家": "Cantonese restaurant",
  "茶楼": "Tea restaurant",
};
const TIME_NOTE_EN: Record<string, string> = {
  "从这里出发": "Start here",
  "傍晚后体验更合理": "Better after dusk",
  "适合下午或晚间的娱乐段": "Better in the afternoon or evening",
  "上午体力或户外段": "Morning outdoor segment",
  "下午到傍晚更适合逛街": "Best from afternoon to early evening",
  "早茶/早餐时段": "Breakfast or brunch window",
  "适合作为下午茶或休息点": "Afternoon tea or rest stop",
  "晚餐时段更合理": "Dinner window",
  "避开正峰的正餐安排": "Off-peak meal window",
};

function displayPlanName(name: string | undefined, language: Language, fallback: string) {
  if (!name) return fallback;
  if (language !== "en") return name;
  if (name.startsWith("备选方案")) return name.replace("备选方案", "Alternative ");
  return PLAN_NAME_EN[name] || name;
}

function displayMode(mode: string | undefined, language: Language) {
  if (!mode) return language === "en" ? "Walking" : "步行";
  return language === "en" ? (MODE_EN[mode] || mode) : mode;
}

function isTransitMode(mode: string | undefined) {
  const normalized = String(mode || "").trim().toLowerCase();
  return ["公共交通", "public transit", "transit", "公交", "地铁", "subway", "metro", "bus"].includes(normalized);
}

function shouldTreatAsTransit(connection: Connection | undefined) {
  if (!connection) return false;
  if (isTransitMode(connection.mode)) return true;
  if (!["步行", "Walking", "walking", undefined, ""].includes(connection.mode)) return false;
  const minutes = parseDurationMinutes(connection.time, connection.duration_minutes);
  const meters = parseDistanceMeters(connection.distance, connection.distance_m);
  return Boolean((minutes && minutes > 20) || (meters && meters > 1600));
}

function displayConnectionMode(connection: Connection | undefined, language: Language) {
  if (shouldTreatAsTransit(connection)) return language === "en" ? "Transit" : "公共交通";
  return displayMode(connection?.mode, language);
}

function displayCategory(category: string | undefined, language: Language) {
  if (!category) return "";
  return language === "en" ? (CATEGORY_EN[category] || category) : category;
}

function displayTimeNote(note: string | undefined, language: Language) {
  if (!note) return "";
  return language === "en" ? (TIME_NOTE_EN[note] || note) : note;
}

function displayTag(tag: string, language: Language) {
  if (language !== "en") return tag;
  return TAG_EN[tag] || CATEGORY_EN[tag] || tag;
}

function displayLocalizedText(text: string | undefined, language: Language) {
  if (!text || language !== "en") return text || "";
  let result = text;
  const replacements = [
    ...Object.entries(TAG_EN),
    ...Object.entries(CATEGORY_EN),
    ...Object.entries(TIME_NOTE_EN),
    ["免费", "free"],
    ["付费", "paid"],
    ["适合", "good for"],
    ["休息点", "rest stop"],
  ] as Array<[string, string]>;
  for (const [source, target] of replacements) {
    result = result.replace(new RegExp(source, "g"), target);
  }
  return result;
}

function displayTransitText(text: string | undefined, language: Language) {
  if (!text) return "";
  if (language !== "en") return text;
  return text
    .replace(/公共交通/g, "Transit")
    .replace(/公交/g, "Bus")
    .replace(/地铁/g, "Metro")
    .replace(/步行/g, "Walk")
    .replace(/换乘/g, "transfer")
    .replace(/约/g, "about ")
    .replace(/小时/g, "h")
    .replace(/分钟/g, "min")
    .replace(/公里/g, "km")
    .replace(/米/g, "m");
}

function displayDateLabel(label: string | undefined, language: Language) {
  if (!label) return "";
  if (language !== "en") return label;
  const monthDay = label.match(/^(\d+)月(\d+)日$/);
  if (monthDay) return `${monthDay[1]}/${monthDay[2]}`;
  if (label === "周六") return "Saturday";
  if (label === "周日") return "Sunday";
  const day = label.match(/^第(\d+)天$/);
  if (day) return `Day ${day[1]}`;
  return label.replace("第", "Day ").replace("天", "");
}

function formatDayCount(count: number, language: Language) {
  if (language === "en") return `${count} ${count === 1 ? "day" : "days"}`;
  return `${count}天`;
}

function formatStopCount(count: number, language: Language) {
  if (language === "en") return `${count} ${count === 1 ? "stop" : "stops"}`;
  return `${count}站`;
}

function formatSegmentCount(count: number, language: Language) {
  if (language === "en") return `${count} ${count === 1 ? "transfer" : "transfers"}`;
  return `${count}段转场`;
}

function displayDayTitle(day: ItineraryDay, language: Language, totalDays: number) {
  if (totalDays <= 1) return displayDateLabel(day.date_label, language) || (language === "en" ? "Today" : "当天");
  return language === "en" ? `Day ${day.day_index}` : day.title;
}

function asDays(plan: Itinerary): ItineraryDay[] {
  if (plan.days?.length) return plan.days;
  return [{
    day_index: 1,
    title: "Day 1",
    date_label: "第1天",
    start_time: plan.blocks[0]?.start_time || "10:00",
    end_time: plan.blocks[plan.blocks.length - 1]?.end_time || "",
    total_duration: plan.total_duration,
    total_price: plan.total_price,
    blocks: plan.blocks,
    connections: plan.connections,
  }];
}

function toNumber(value: number | string | undefined) {
  const parsed = typeof value === "string" ? Number(value) : value;
  return Number.isFinite(parsed) ? parsed as number : null;
}

interface CanvasProps {
  itinerary: Itinerary | null;
  onClose: () => void;
  onItineraryUpdate?: (itinerary: Itinerary) => void;
  onAdjustResult?: (userMsg: string, reply: string, itinerary?: Itinerary) => void;
  sessionId: string;
  language: Language;
}

export default function Canvas({ itinerary, onClose, onItineraryUpdate, onAdjustResult, sessionId, language }: CanvasProps) {
  const [activePlan, setActivePlan] = useState<Itinerary | null>(itinerary);
  const [activeDay, setActiveDay] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [adjusting, setAdjusting] = useState<string | null>(null);
  const text = CANVAS_TEXT[language];

  useEffect(() => {
    setActivePlan(itinerary);
    setActiveDay(1);
    setSelectedId(null);
  }, [itinerary]);

  const plans = useMemo(() => {
    if (!itinerary) return [];
    return [itinerary, ...(itinerary.alternatives || [])];
  }, [itinerary]);

  if (!activePlan) return null;

  const days = asDays(activePlan);
  const currentDay = days.find((day) => day.day_index === activeDay) || days[0];
  const mapPois = activePlan.map_pois || [];
  const selectedBlock = currentDay.blocks.find((block) => block.id === selectedId) || mapPois.find((block) => block.id === selectedId);
  const showDayNav = days.length > 1;

  const summarizePlanSwitch = (plan: Itinerary, index: number) => {
    const planName = displayPlanName(plan.plan_name, language, language === "en" ? `Option ${index + 1}` : `方案${index + 1}`);
    const firstDay = asDays(plan)[0];
    const stopCount = (firstDay?.blocks || plan.blocks || []).filter((block) => !block.is_start).length;
    const startLine = plan.start_transfer
      ? (
        language === "en"
          ? `\n- Start access: ${plan.start_transfer.from_name} → ${plan.start_transfer.to_name}, ${displayConnectionMode(plan.start_transfer, language)} ${formatDurationLabel(plan.start_transfer.time, language, plan.start_transfer.duration_minutes)}`
          : `\n- 起点接入：${plan.start_transfer.from_name} → ${plan.start_transfer.to_name}，${displayConnectionMode(plan.start_transfer, language)}约${formatDurationLabel(plan.start_transfer.time, language, plan.start_transfer.duration_minutes)}`
      )
      : "";
    return language === "en"
      ? `Switched to **${planName}**.\n- Duration: ${plan.total_duration}min\n- Cost: ¥${plan.total_price}\n- Stops: ${stopCount}${startLine}`
      : `已切换到 **${planName}**。\n- 总时长：${plan.total_duration}分钟\n- 预计花费：¥${plan.total_price}\n- 地点数：${stopCount}${startLine}`;
  };

  const summarizeAdjustment = (action: string, nextPlan: Itinerary, previousPlan: Itinerary | null) => {
    const actionLabel = text.actions[action as keyof typeof text.actions] || action;
    const firstDay = asDays(nextPlan)[0];
    const routeStops = (firstDay?.blocks || nextPlan.blocks || []).filter((block) => !block.is_start);
    const routeLine = routeStops.slice(0, 6).map((block) => shortPlaceName(block.name)).join(" → ");
    const deltaText = (label: string, next: number, prev?: number | null, unit = "") => {
      if (prev === undefined || prev === null || !Number.isFinite(prev)) return `${label}: ${next}${unit}`;
      const delta = next - prev;
      const sign = delta > 0 ? "+" : "";
      return `${label}: ${next}${unit} (${sign}${delta}${unit})`;
    };
    const startLine = nextPlan.start_transfer
      ? (
        language === "en"
          ? `\n- Start access: ${nextPlan.start_transfer.from_name} → ${nextPlan.start_transfer.to_name}, ${displayConnectionMode(nextPlan.start_transfer, language)} ${formatDurationLabel(nextPlan.start_transfer.time, language, nextPlan.start_transfer.duration_minutes)}`
          : `\n- 起点接入：${nextPlan.start_transfer.from_name} → ${nextPlan.start_transfer.to_name}，${displayConnectionMode(nextPlan.start_transfer, language)}约${formatDurationLabel(nextPlan.start_transfer.time, language, nextPlan.start_transfer.duration_minutes)}`
      )
      : "";

    if (language === "en") {
      return [
        `Adjusted with **${actionLabel}**.`,
        `- ${deltaText("Duration", nextPlan.total_duration, previousPlan?.total_duration, "min")}`,
        `- ${deltaText("Cost", nextPlan.total_price, previousPlan?.total_price, "")}`,
        `- Stops: ${routeStops.length}`,
        startLine.trim(),
        routeLine ? `- New route: ${routeLine}` : "",
      ].filter(Boolean).join("\n");
    }
    return [
      `已按 **${actionLabel}** 重新调整。`,
      `- ${deltaText("总时长", nextPlan.total_duration, previousPlan?.total_duration, "分钟")}`,
      `- ${deltaText("预计花费", nextPlan.total_price, previousPlan?.total_price, "元")}`,
      `- 地点数：${routeStops.length}`,
      startLine.trim(),
      routeLine ? `- 新路线：${routeLine}` : "",
    ].filter(Boolean).join("\n");
  };

  const selectPlan = (plan: Itinerary, index: number) => {
    const samePlan = plan === activePlan;
    setActivePlan(plan);
    setActiveDay(1);
    setSelectedId(null);
    if (!samePlan) {
      const planName = displayPlanName(plan.plan_name, language, language === "en" ? `Option ${index + 1}` : `方案${index + 1}`);
      onAdjustResult?.(
        language === "en" ? `Switch to ${planName}` : `切换到${planName}`,
        summarizePlanSwitch(plan, index)
      );
    }
  };

  const selectDay = (dayIndex: number) => {
    setActiveDay(dayIndex);
    setSelectedId(null);
  };

  const ACTION_MESSAGES: Record<Language, Record<string, string>> = {
    zh: {
      less_walking: "我不想走太多路，请帮我重新规划，选近一点的地点",
      lower_budget: "请帮我提高性价比，重新分配预算",
      less_queue: "我不想排队，请帮我重新规划，避开排队多的地方",
      replace_poi: "请帮我换掉行程中的餐厅",
    },
    en: {
      less_walking: "Please reduce walking and choose closer stops.",
      lower_budget: "Please improve value and rebalance the budget.",
      less_queue: "Please avoid places with long queues.",
      replace_poi: "Please swap the restaurant in the itinerary.",
    },
  };

  const handleAdjust = async (action: string) => {
    const userMsg = ACTION_MESSAGES[language][action] || (language === "en" ? `Please adjust the itinerary: ${action}` : `请帮我调整行程：${action}`);
    const previousPlan = activePlan;
    const payload = {
      current_itinerary: activePlan,
      current_plan_name: activePlan?.plan_name,
      current_style: activePlan?.style,
      category: action === "replace_poi" ? "餐厅" : undefined,
    };
    setAdjusting(action);
    try {
      const data = await apiPost<{ message: string; reply: string; itinerary?: Itinerary; alternatives?: Itinerary[] }>(
        "/api/itinerary/adjust",
        { action, session_id: sessionId, payload },
        { timeoutMs: 120000 }
      );
      if (data.itinerary) {
        data.itinerary.alternatives = data.alternatives || data.itinerary.alternatives || [];
        setActivePlan(data.itinerary);
        setActiveDay(1);
        setSelectedId(null);
        onItineraryUpdate?.(data.itinerary);
      }
      const reply = data.itinerary ? summarizeAdjustment(action, data.itinerary, previousPlan) : data.reply;
      onAdjustResult?.(data.message || userMsg, reply, data.itinerary);
    } catch {
      onAdjustResult?.(
        userMsg,
        language === "en"
          ? "Adjustment failed. The backend did not return a usable plan. Please retry later."
          : "调整失败，后端没有返回可用方案。请稍后重试。"
      );
    } finally {
      setAdjusting(null);
    }
  };

  return (
    <div className="flex h-full flex-col bg-slate-100">
      <div className="shrink-0 border-b border-slate-200 bg-white/95 px-5 py-4 shadow-sm backdrop-blur">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-600">{text.lab}</div>
            <h2 className="mt-1 truncate text-2xl font-semibold tracking-tight text-slate-950">
              {displayPlanName(activePlan.plan_name, language, text.routePlan)}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="h-9 w-9 shrink-0 rounded-full border border-slate-200 text-slate-400 transition hover:bg-slate-50 hover:text-slate-700"
            aria-label={language === "en" ? "Close route panel" : "关闭路线面板"}
          >
            ×
          </button>
        </div>

        <div className="mt-4 grid grid-cols-3 gap-2">
          <Stat label={text.totalDuration} value={formatDurationLabel(undefined, language, activePlan.total_duration)} />
          <Stat label={text.totalCost} value={`¥${activePlan.total_price}`} />
          <Stat label={text.transferDistance} value={formatDistance(activePlan.total_distance, language)} />
        </div>

        <div className="mt-4 flex gap-2 overflow-x-auto pb-1">
          {plans.map((plan, index) => {
            const active = plan === activePlan || plan.plan_name === activePlan.plan_name;
            return (
              <button
                key={`${plan.plan_name || "plan"}-${index}`}
                onClick={() => selectPlan(plan, index)}
                className={`min-w-44 rounded-lg border px-3 py-2.5 text-left transition ${
                  active
                    ? "border-blue-500 bg-blue-50 text-blue-800 shadow-sm"
                    : "border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50"
                }`}
              >
                <div className="text-sm font-semibold">{displayPlanName(plan.plan_name, language, language === "en" ? `Option ${index + 1}` : `方案${index + 1}`)}</div>
                 <div className="mt-1 text-xs opacity-80">{formatDayCount(plan.days?.length || 1, language)} · {formatDurationLabel(undefined, language, plan.total_duration)} · ¥{plan.total_price}</div>
              </button>
            );
          })}
        </div>

      </div>

      <div className={`grid min-h-0 flex-1 ${showDayNav ? "grid-cols-[112px_1fr] lg:grid-cols-[132px_1fr]" : "grid-cols-1"}`}>
        {showDayNav && <aside className="min-h-0 overflow-y-auto border-r border-slate-200 bg-white/80 p-3">
          <div className="space-y-2">
            {days.map((day) => {
              const active = day.day_index === currentDay.day_index;
              return (
                <button
                  key={day.day_index}
                  onClick={() => selectDay(day.day_index)}
                  className={`w-full rounded-lg border px-3 py-3 text-left transition ${
                    active ? "border-blue-500 bg-blue-50 text-blue-800 shadow-sm" : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                  }`}
                >
                  <div className="text-sm font-semibold">{displayDayTitle(day, language, days.length)}</div>
                  <div className="mt-1 text-xs">{displayDateLabel(day.date_label, language)}</div>
                  <div className="mt-2 text-xs text-slate-500">¥{day.total_price} · {formatStopCount(day.blocks.filter((block) => !block.is_start).length, language)}</div>
                </button>
              );
            })}
          </div>
        </aside>}

        <div className="min-h-0 overflow-y-auto p-4 lg:p-5">
          <RouteMap
            day={currentDay}
            mapPois={mapPois}
            selectedId={selectedId}
            selectedBlock={selectedBlock}
            onSelect={setSelectedId}
            language={language}
            totalDays={days.length}
            startTransfer={activeDay === 1 ? activePlan.start_transfer : undefined}
          />
          <Timeline day={currentDay} selectedId={selectedId} onSelect={setSelectedId} language={language} />
        </div>
      </div>

      <div className="shrink-0 border-t border-slate-200 bg-white/95 px-4 py-3 shadow-[0_-10px_24px_rgba(15,23,42,0.05)]">
        <div className="flex items-center gap-2 overflow-x-auto">
          <span className="shrink-0 text-xs font-medium text-slate-400">{text.quickAdjust}</span>
          {[
            { key: "less_walking", label: text.actions.less_walking },
            { key: "lower_budget", label: text.actions.lower_budget },
            { key: "less_queue", label: text.actions.less_queue },
            { key: "replace_poi", label: text.actions.replace_poi },
          ].map((btn) => (
            <button
              key={btn.key}
              onClick={() => handleAdjust(btn.key)}
              disabled={adjusting !== null}
              className={`rounded-full border px-4 py-2 text-xs font-medium transition ${
                adjusting === btn.key
                  ? "border-blue-300 bg-blue-50 text-blue-700"
                  : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50"
              } disabled:cursor-not-allowed disabled:opacity-60`}
            >
              {adjusting === btn.key ? text.adjusting : btn.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-1 text-lg font-semibold tracking-tight text-slate-950">{value}</div>
    </div>
  );
}

function RouteMap({
  day,
  mapPois,
  selectedId,
  selectedBlock,
  onSelect,
  language,
  totalDays,
  startTransfer,
}: {
  day: ItineraryDay;
  mapPois: ItineraryBlock[];
  selectedId: string | null;
  selectedBlock?: ItineraryBlock;
  onSelect: (id: string | null) => void;
  language: Language;
  totalDays: number;
  startTransfer?: Connection;
}) {
  const text = CANVAS_TEXT[language];
  const routeBlocks = useMemo(() => day.blocks.filter((block) => !block.is_start), [day.blocks]);
  const routeBlockIds = useMemo(() => new Set(routeBlocks.map((block) => block.id)), [routeBlocks]);
  const routeConnections = useMemo(
    () => day.connections.filter((conn) => routeBlockIds.has(conn.from) && routeBlockIds.has(conn.to)),
    [day.connections, routeBlockIds],
  );
  const nearbyPois = useMemo(() => filterNearbyPois(routeBlocks, mapPois), [routeBlocks, mapPois]);
  const projected = useMemo(() => projectRouteBlueprint(routeBlocks, nearbyPois), [routeBlocks, nearbyPois]);
  const routeSegments = projected.route.slice(0, -1).map((point, index) => ({
    from: point,
    to: projected.route[index + 1],
    connection: routeConnections[index],
  }));
  const startTransferSegments = startTransfer?.transit_detail?.segments || [];
  const routeMarkerLabel = (index: number) => {
    const block = projected.route[index]?.block;
    if (!block) return String(index + 1);
    return String(index + 1);
  };

  return (
    <div className="mb-4 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
        <div>
          <h3 className="mt-1 text-lg font-semibold text-slate-950">
            {displayDayTitle(day, language, totalDays)}
            {totalDays > 1 && day.date_label ? ` · ${displayDateLabel(day.date_label, language)}` : ""}
          </h3>
        </div>
        <div className="rounded-lg bg-slate-50 px-3 py-2 text-right text-xs text-slate-500">
          <div>{day.start_time} - {day.end_time}</div>
          <div className="mt-1">{formatStopCount(routeBlocks.length, language)} · {formatSegmentCount(routeConnections.length, language)}</div>
        </div>
      </div>

      {startTransfer && (
        <div className="border-b border-blue-100 bg-blue-50/70 px-5 py-3 text-sm text-slate-700">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-blue-600 px-2 py-0.5 text-xs font-semibold text-white">{text.startAccess}</span>
            <span className="font-semibold text-slate-950">{startTransfer.from_name || (language === "en" ? "Start" : "起点")}</span>
            <span className="text-slate-400">→</span>
            <span className="font-semibold text-slate-950">{startTransfer.to_name}</span>
            {startTransferSegments.length > 0 && (
              <span className="basis-full rounded-lg border border-blue-100 bg-white/85 p-3 text-xs leading-5 text-slate-600 shadow-sm">
                <span className="block font-semibold text-slate-900">
                  {displayTransitText(startTransfer.transit_detail?.summary, language) || (language === "en" ? "Transit plan" : "公共交通方案")}
                </span>
                <span className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
                  {startTransferSegments.slice(0, 5).map((segment, index) => (
                    <span key={`${segment}-${index}`} className="max-w-[320px] truncate">
                      {index + 1}. {displayTransitText(segment, language)}
                    </span>
                  ))}
                </span>
              </span>
            )}
            <span className="text-xs text-slate-500">
              {displayConnectionMode(startTransfer, language)} · {formatDistanceLabel(startTransfer.distance, language, startTransfer.distance_m)} · {formatDurationLabel(startTransfer.time, language, startTransfer.duration_minutes)}
            </span>
          </div>
        </div>
      )}

      <div
        className="relative h-[400px] overflow-hidden bg-[#f7fbff]"
        onClick={() => onSelect(null)}
      >
        {AMAP_JS_KEY && routeBlocks.some((block) => blockLngLat(block)) ? (
          <AmapRouteLayer
            routeBlocks={routeBlocks}
            nearbyPois={nearbyPois}
            routeConnections={routeConnections}
            selectedId={selectedId}
            onSelect={onSelect}
            language={language}
          />
        ) : (
        <>
        <RouteMapBackdrop route={projected.route} pois={projected.pois} />
        <div className="absolute inset-0 bg-gradient-to-b from-white/50 via-transparent to-blue-950/5" />
        <div className="absolute inset-0">
          <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
            {routeSegments.map((segment) => (
              <g key={`${segment.from.block.id}-${segment.to.block.id}`}>
                <line
                  x1={segment.from.x}
                  y1={segment.from.y}
                  x2={segment.to.x}
                  y2={segment.to.y}
                  stroke="rgba(255,255,255,0.95)"
                  strokeWidth="1.2"
                  strokeLinecap="round"
                />
                <line
                  x1={segment.from.x}
                  y1={segment.from.y}
                  x2={segment.to.x}
                  y2={segment.to.y}
                  stroke={shouldTreatAsTransit(segment.connection) ? "#2563eb" : "#0284c7"}
                  strokeWidth="0.58"
                  strokeLinecap="round"
                />
              </g>
            ))}
          </svg>

        </div>

        <div
          className="absolute left-4 top-4 z-20 flex items-center gap-2 rounded-full border border-white/80 bg-white/90 px-3 py-1.5 text-xs text-slate-600 shadow-sm backdrop-blur"
          onMouseDown={(event) => event.stopPropagation()}
        >
          <span className="inline-flex h-2.5 w-2.5 rounded-full bg-sky-500" /> {text.route}
          <span className="ml-2 inline-flex h-2.5 w-2.5 rounded-full bg-white ring-2 ring-slate-300" /> {text.nearbyPoi}
        </div>

        <div
          className="absolute inset-0"
        >
        {projected.pois.map((point) => {
          const style = getStyle(point.block.type);
          const active = selectedId === point.block.id;
          return (
            <button
              key={point.block.id}
              onClick={(event) => {
                event.stopPropagation();
                onSelect(active ? null : point.block.id);
              }}
              onMouseDown={(event) => event.stopPropagation()}
              className={`absolute z-10 flex h-8 w-8 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-2 bg-white/95 text-xs shadow-[0_10px_24px_rgba(15,23,42,0.14)] transition hover:scale-110 ${
                active ? "border-blue-500 ring-4 ring-blue-100" : `${style.border} ring-2 ring-white/90`
              } ${style.text}`}
              style={{ left: `${point.x}%`, top: `${point.y}%` }}
              title={point.block.name}
            >
              {point.block.icon}
            </button>
          );
        })}

        {projected.route.map((point, index) => {
          const active = selectedId === point.block.id;
          const markerColor = routeMarkerColor(index, Boolean(point.block.is_start));
          return (
            <div
              key={point.block.id}
              onClick={(event) => {
                event.stopPropagation();
                onSelect(active ? null : point.block.id);
              }}
              onMouseDown={(event) => event.stopPropagation()}
              className="absolute z-20 flex -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-1"
              style={{ left: `${point.x}%`, top: `${point.y}%` }}
            >
              <button
                onClick={(event) => {
                  event.stopPropagation();
                  onSelect(active ? null : point.block.id);
                }}
                onMouseDown={(event) => event.stopPropagation()}
                className={`flex h-9 w-9 items-center justify-center rounded-full border-2 text-xs font-bold text-white shadow-[0_12px_28px_rgba(37,99,235,0.28)] transition hover:scale-110 ${
                  active ? "border-white ring-4 ring-blue-100" : "border-white ring-4 ring-white/90"
                }`}
                style={{ backgroundColor: markerColor }}
                title={point.block.name}
              >
                {routeMarkerLabel(index)}
              </button>
              <span
                className="max-w-[112px] truncate rounded-full border border-slate-200 bg-white/95 px-2 py-0.5 text-[10px] font-semibold text-slate-700 shadow-sm"
                title={point.block.name}
              >
                {shortPlaceName(point.block.name)}
              </span>
            </div>
          );
        })}
        </div>
        </>
        )}

        {selectedBlock && (
          <div
            className="absolute bottom-4 left-4 right-4 z-30 rounded-lg border border-slate-200 bg-white/95 p-4 shadow-2xl backdrop-blur md:bottom-auto md:left-auto md:right-4 md:top-16 md:w-[360px]"
            onMouseDown={(event) => event.stopPropagation()}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start gap-3">
              <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-lg ${getStyle(selectedBlock.type).bg} ${getStyle(selectedBlock.type).text}`}>
                {selectedBlock.icon}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-3">
                  <h4 className="line-clamp-2 font-semibold text-slate-950">{selectedBlock.name}</h4>
                  <button
                    onClick={(event) => {
                      event.stopPropagation();
                      onSelect(null);
                    }}
                    className="text-sm text-slate-400 hover:text-slate-700"
                  >
                    ×
                  </button>
                </div>
                <p className="mt-1 line-clamp-2 text-sm text-slate-600">{selectedBlock.reason || selectedBlock.address}</p>
                {selectedBlock.recommendation && (
                  <p className="mt-2 line-clamp-2 text-xs leading-5 text-slate-500">{selectedBlock.recommendation}</p>
                )}
                <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-500">
                  {selectedBlock.start_time ? <span>{selectedBlock.start_time} - {selectedBlock.end_time}</span> : <span>{displayCategory(selectedBlock.category, language) || text.nearby}</span>}
                  <span>{formatDurationLabel(undefined, language, selectedBlock.duration)}</span>
                  <span>¥{selectedBlock.price}</span>
                  {selectedBlock.rating ? <span>{text.rating} {selectedBlock.rating}</span> : null}
                </div>
                {selectedBlock.address && <div className="mt-2 line-clamp-1 text-xs text-slate-400">{selectedBlock.address}</div>}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function AmapRouteLayer({
  routeBlocks,
  nearbyPois,
  routeConnections,
  selectedId,
  onSelect,
  language,
}: {
  routeBlocks: ItineraryBlock[];
  nearbyPois: ItineraryBlock[];
  routeConnections: Connection[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  language: Language;
}) {
  const text = CANVAS_TEXT[language];
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<any>(null);
  const overlaysRef = useRef<any[]>([]);
  const onSelectRef = useRef(onSelect);
  const [AMapObj, setAMapObj] = useState<any>(null);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  useEffect(() => {
    let disposed = false;
    loadAmapCanvasSdk()
      .then((AMap) => {
        if (disposed || !containerRef.current) return;
        const firstCoord = firstRouteCoord(routeBlocks) || { lng: 113.2644, lat: 23.1291 };
        const map = new AMap.Map(containerRef.current, {
          center: [firstCoord.lng, firstCoord.lat],
          zoom: 15,
          viewMode: "2D",
          resizeEnable: true,
          showLabel: true,
          mapStyle: "amap://styles/normal",
          features: ["bg", "road", "building", "point"],
          dragEnable: false,
          zoomEnable: false,
          doubleClickZoom: false,
          keyboardEnable: false,
          scrollWheel: false,
          isHotspot: false,
        });
        map.on("click", () => onSelectRef.current(null));
        mapRef.current = map;
        setAMapObj(AMap);
      })
      .catch(() => setLoadError(true));

    return () => {
      disposed = true;
      clearAmapOverlays(mapRef.current, overlaysRef.current);
      overlaysRef.current = [];
      if (mapRef.current?.destroy) mapRef.current.destroy();
      mapRef.current = null;
    };
    // Create the AMap instance once. Route overlays update in the effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!AMapObj || !map) return;

    clearAmapOverlays(map, overlaysRef.current);
    const overlays: any[] = [];
    const routeById = new Map(routeBlocks.map((block) => [block.id, block]));

    routeConnections.forEach((connection) => {
      const path = connectionLngLatPath(connection, routeById);
      if (path.length < 2) return;
      const polyline = new AMapObj.Polyline({
        path: path.map((point) => new AMapObj.LngLat(point.lng, point.lat)),
        strokeColor: shouldTreatAsTransit(connection) ? "#2563eb" : "#0284c7",
        strokeOpacity: 0.92,
        strokeWeight: 5,
        lineJoin: "round",
        lineCap: "round",
        zIndex: 80,
      });
      overlays.push(polyline);

    });

    nearbyPois.slice(0, 14).forEach((block) => {
      const coord = blockLngLat(block);
      if (!coord) return;
      const marker = new AMapObj.Marker({
        position: new AMapObj.LngLat(coord.lng, coord.lat),
        anchor: "center",
        content: nearbyPoiMarkerHtml(block),
        zIndex: 70,
      });
      marker.on("click", () => onSelectRef.current(selectedId === block.id ? null : block.id));
      overlays.push(marker);
    });

    routeBlocks.forEach((block, index) => {
      const coord = blockLngLat(block);
      if (!coord) return;
      const marker = new AMapObj.Marker({
        position: new AMapObj.LngLat(coord.lng, coord.lat),
        anchor: "bottom-center",
        content: routeMarkerHtml(block, index, selectedId === block.id),
        zIndex: 120 + index,
      });
      marker.on("click", () => onSelectRef.current(selectedId === block.id ? null : block.id));
      overlays.push(marker);
    });

    map.add(overlays);
    overlaysRef.current = overlays;
    try {
      map.setFitView(overlays, false, [56, 56, 56, 56], 17);
    } catch {
      const firstCoord = firstRouteCoord(routeBlocks);
      if (firstCoord) map.setCenter([firstCoord.lng, firstCoord.lat]);
    }
  }, [AMapObj, language, nearbyPois, routeBlocks, routeConnections, selectedId]);

  if (loadError) {
    return (
      <div className="absolute inset-0 flex items-center justify-center bg-slate-50 text-sm text-slate-500">
        {language === "en" ? "AMap failed to load. Showing route data only." : "高德地图加载失败，请检查 JS Key、域名白名单或网络。"}
      </div>
    );
  }

  return (
    <div className="absolute inset-0">
      <div ref={containerRef} className="absolute inset-0 bg-slate-100" />
      {!AMapObj && (
        <div className="absolute inset-0 flex items-center justify-center bg-white/70 text-sm text-slate-500 backdrop-blur-sm">
          {language === "en" ? "Loading AMap..." : "正在加载高德地图..."}
        </div>
      )}
      <div className="absolute left-4 top-4 z-20 flex items-center gap-2 rounded-full border border-white/80 bg-white/90 px-3 py-1.5 text-xs text-slate-600 shadow-sm backdrop-blur">
        <span className="inline-flex h-2.5 w-2.5 rounded-full bg-sky-500" /> {text.route}
        <span className="ml-2 inline-flex h-2.5 w-2.5 rounded-full bg-white ring-2 ring-slate-300" /> {text.nearbyPoi}
      </div>
    </div>
  );
}

function loadAmapCanvasSdk(): Promise<any> {
  if (!AMAP_JS_KEY || typeof window === "undefined") return Promise.reject(new Error("missing amap js key"));
  const scopedWindow = window as typeof window & {
    AMap?: any;
    _AMapSecurityConfig?: { securityJsCode?: string };
    __roamAmapLoading?: Promise<any>;
    __roamAmapCanvasLoading?: Promise<any>;
    __roamAmapCanvasReady?: () => void;
  };
  if (scopedWindow.AMap?.Map) return Promise.resolve(scopedWindow.AMap);
  if (scopedWindow.__roamAmapLoading) return scopedWindow.__roamAmapLoading.then(() => scopedWindow.AMap);
  if (scopedWindow.__roamAmapCanvasLoading) return scopedWindow.__roamAmapCanvasLoading;
  if (AMAP_SECURITY_JS_CODE) {
    scopedWindow._AMapSecurityConfig = { securityJsCode: AMAP_SECURITY_JS_CODE };
  }

  scopedWindow.__roamAmapCanvasLoading = new Promise((resolve, reject) => {
    scopedWindow.__roamAmapCanvasReady = () => resolve(scopedWindow.AMap);
    const script = document.createElement("script");
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(AMAP_JS_KEY)}&plugin=AMap.Scale&callback=__roamAmapCanvasReady`;
    script.async = true;
    script.dataset.roamAmap = "canvas";
    script.onerror = () => reject(new Error("amap js load failed"));
    document.head.appendChild(script);
  });

  return scopedWindow.__roamAmapCanvasLoading;
}

function clearAmapOverlays(map: any, overlays: any[]) {
  if (!map || !overlays.length) return;
  try {
    map.remove(overlays);
  } catch {
    overlays.forEach((overlay) => {
      try {
        overlay?.setMap?.(null);
      } catch {
        // Ignore overlay cleanup errors from AMap internals.
      }
    });
  }
}

function firstRouteCoord(routeBlocks: ItineraryBlock[]) {
  for (const block of routeBlocks) {
    const coord = blockLngLat(block);
    if (coord) return coord;
  }
  return null;
}

function connectionLngLatPath(connection: Connection, routeById: Map<string, ItineraryBlock>) {
  const routePath = (connection.route_path || [])
    .map((point) => ({ lng: toNumber(point.lng), lat: toNumber(point.lat) }))
    .filter((point): point is { lng: number; lat: number } => point.lng !== null && point.lat !== null);
  if (routePath.length >= 2) return routePath;

  const fromBlock = routeById.get(connection.from);
  const toBlock = routeById.get(connection.to);
  const from = fromBlock ? blockLngLat(fromBlock) : null;
  const to = toBlock ? blockLngLat(toBlock) : null;
  return from && to ? [from, to] : [];
}

function routeMarkerHtml(block: ItineraryBlock, index: number, active: boolean) {
  const color = routeMarkerColor(index, Boolean(block.is_start));
  const name = escapeHtml(shortPlaceName(block.name));
  const scale = active ? "scale(1.08)" : "scale(1)";
  return `
    <div style="display:flex;flex-direction:column;align-items:center;gap:4px;transform:${scale};">
      <div style="width:34px;height:34px;border-radius:999px;background:${color};border:3px solid #fff;box-shadow:0 10px 24px rgba(37,99,235,.28);display:flex;align-items:center;justify-content:center;color:#fff;font-size:14px;font-weight:800;">
        ${index + 1}
      </div>
      <div style="max-width:112px;padding:2px 7px;border-radius:999px;background:rgba(255,255,255,.96);border:1px solid rgba(203,213,225,.95);box-shadow:0 6px 14px rgba(15,23,42,.14);font-size:11px;font-weight:700;color:#0f172a;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
        ${name}
      </div>
    </div>
  `;
}

function nearbyPoiMarkerHtml(block: ItineraryBlock) {
  const style = getStyle(block.type);
  const icon = escapeHtml(block.icon || "");
  return `
    <div title="${escapeHtml(block.name)}" style="width:28px;height:28px;border-radius:999px;background:rgba(255,255,255,.96);border:2px solid ${style.stroke};box-shadow:0 7px 18px rgba(15,23,42,.15);display:flex;align-items:center;justify-content:center;font-size:13px;">
      ${icon}
    </div>
  `;
}

function escapeHtml(value: string) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function Timeline({
  day,
  selectedId,
  onSelect,
  language,
}: {
  day: ItineraryDay;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  language: Language;
}) {
  const text = CANVAS_TEXT[language];
  const [openConnection, setOpenConnection] = useState<string | null>(null);
  const [transitDetails, setTransitDetails] = useState<Record<string, NonNullable<Connection["transit_detail"]>>>({});
  const [loadingTransit, setLoadingTransit] = useState<string | null>(null);
  const visibleBlocks = useMemo(() => day.blocks.filter((block) => !block.is_start), [day.blocks]);
  const visibleIds = useMemo(() => new Set(visibleBlocks.map((block) => block.id)), [visibleBlocks]);
  const visibleConnections = useMemo(
    () => day.connections.filter((conn) => visibleIds.has(conn.from) && visibleIds.has(conn.to)),
    [day.connections, visibleIds],
  );

  useEffect(() => {
    setOpenConnection(null);
    setTransitDetails({});
    setLoadingTransit(null);
  }, [day.day_index]);

  const fetchTransitDetail = async (connection: Connection) => {
    const key = `${connection.from}-${connection.to}`;
    if (connection.transit_detail?.segments?.length || transitDetails[key] || loadingTransit === key) return;
    const origin = `${connection.from_lng},${connection.from_lat}`;
    const destination = `${connection.to_lng},${connection.to_lat}`;
    if (!connection.from_lng || !connection.from_lat || !connection.to_lng || !connection.to_lat) return;
    setLoadingTransit(key);
    try {
      const detail = await apiPost<NonNullable<Connection["transit_detail"]>>(
        "/api/route/transit",
        { origin, destination, city: connection.city || "" },
        { timeoutMs: 12000 }
      );
      setTransitDetails((prev) => ({ ...prev, [key]: detail }));
    } catch {
      setTransitDetails((prev) => ({
        ...prev,
        [key]: {
          summary: language === "en" ? "Transit details unavailable" : "暂未获取到公共交通换乘明细",
          segments: [],
        },
      }));
    } finally {
      setLoadingTransit(null);
    }
  };

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">{text.checklist}</div>
          <h3 className="mt-1 text-lg font-semibold text-slate-950">{text.dayChecklist}</h3>
        </div>
        <div className="rounded-full bg-slate-50 px-3 py-1 text-xs text-slate-500">{text.timeOrder}</div>
      </div>
      <div className="relative space-y-3">
        <div className="absolute bottom-8 left-[86px] top-8 w-px bg-slate-200" />
        {visibleBlocks.map((block, index) => {
          const style = getStyle(block.type);
          const connection = visibleConnections[index];
          const selected = selectedId === block.id;
          const connectionKey = connection ? `${connection.from}-${connection.to}` : "";
          const lazyTransitDetail = connectionKey ? transitDetails[connectionKey] : undefined;
          const transitDetail = connection?.transit_detail || lazyTransitDetail;
          const isTransit = Boolean(connection && shouldTreatAsTransit(connection));
          const hasTransitDetail = Boolean(transitDetail);
          const isTransitLoading = loadingTransit === connectionKey;
          return (
            <div key={block.id}>
              <button
                onClick={() => onSelect(selected ? null : block.id)}
                className={`relative grid w-full grid-cols-[98px_1fr] gap-4 rounded-lg border p-4 text-left transition hover:shadow-md ${
                  selected ? "border-blue-500 bg-blue-50 ring-2 ring-blue-100" : `${style.border} ${style.bg}`
                }`}
              >
                <div className="text-sm">
                  <div className="font-semibold text-slate-950">{block.start_time || "--:--"}</div>
                  <div className="mt-1 text-xs text-slate-500">{block.end_time || ""}</div>
                </div>
                <div className="min-w-0">
                  <div className="flex items-start gap-3">
                    <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-white bg-white/80 ${style.text} shadow-sm`}>
                      {block.icon}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold text-slate-400">{String(index + 1).padStart(2, "0")}</span>
                        <h4 className="truncate font-semibold text-slate-950">{block.name}</h4>
                      </div>
                       <div className="mt-1 text-sm text-slate-500">{formatDurationLabel(undefined, language, block.duration)} · ¥{block.price}</div>
                      {block.reason && <div className="mt-2 line-clamp-2 text-xs leading-5 text-slate-600">{displayLocalizedText(block.reason, language)}</div>}
                      {block.time_note && <div className="mt-1 text-xs text-blue-600">{displayTimeNote(block.time_note, language)}</div>}
                      <div className="mt-3 flex flex-wrap gap-1">
                        {(block.tags || []).slice(0, 4).map((tag) => (
                          <span key={tag} className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600">{displayTag(tag, language)}</span>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </button>
              {connection && (
                <div className="ml-[114px] mt-2">
                  <button
                    type="button"
                    onClick={async () => {
                      if (!hasTransitDetail && !isTransit) return;
                      const nextOpen = openConnection === connectionKey ? null : connectionKey;
                      setOpenConnection(nextOpen);
                      if (nextOpen && isTransit) await fetchTransitDetail(connection);
                    }}
                    className={`inline-flex rounded-full bg-white px-3 py-1.5 text-xs text-slate-500 shadow-sm ring-1 ring-slate-200 transition ${
                      hasTransitDetail || isTransit ? "hover:bg-blue-50 hover:text-blue-700 hover:ring-blue-200" : "cursor-default"
                    }`}
                  >
                    {displayConnectionMode(connection, language)} · {formatDistanceLabel(connection.distance, language, connection.distance_m)} · {formatDurationLabel(connection.time, language, connection.duration_minutes)}
                    {isTransitLoading ? (language === "en" ? " · loading" : " · 加载中") : ""}
                  </button>
                  {hasTransitDetail && openConnection === connectionKey && (
                    <div className="mt-2 max-w-xl rounded-lg border border-slate-200 bg-white p-3 text-xs leading-5 text-slate-600 shadow-sm">
                      <div className="font-semibold text-slate-900">
                        {displayTransitText(transitDetail?.summary, language)}
                      </div>
                      {transitDetail?.segments?.length ? (
                        <ul className="mt-2 space-y-1">
                          {transitDetail.segments.slice(0, 5).map((segment, idx) => (
                            <li key={`${segment}-${idx}`}>{displayTransitText(segment, language)}</li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

type ProjectedMapPoint = { block: ItineraryBlock; x: number; y: number };

function RouteMapBackdrop({ route, pois }: { route: ProjectedMapPoint[]; pois: ProjectedMapPoint[] }) {
  const routePath = makeSvgPath(route.map((point) => ({ x: point.x, y: point.y })));
  const routeCenterY = route.length
    ? route.reduce((sum, point) => sum + point.y, 0) / route.length
    : 52;
  const routeCenterX = route.length
    ? route.reduce((sum, point) => sum + point.x, 0) / route.length
    : 52;
  const stationPoints = route.slice(0, 8);
  const poiPoints = pois.slice(0, 10);

  return (
    <div className="absolute inset-0 overflow-hidden bg-[#f8fafc]">
      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
        <defs>
          <linearGradient id="roamMapWater" x1="0" x2="1">
            <stop offset="0" stopColor="#dbeafe" />
            <stop offset="1" stopColor="#bae6fd" />
          </linearGradient>
          <filter id="roamMapSoft" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="1.5" stdDeviation="1.2" floodColor="rgba(15,23,42,0.10)" />
          </filter>
        </defs>
        <rect width="100" height="100" fill="#f8fafc" />
        <path d={`M0 ${Math.max(70, routeCenterY + 22)} C18 ${routeCenterY + 13}, 32 ${routeCenterY + 28}, 51 ${routeCenterY + 17} S78 ${routeCenterY + 10}, 100 ${routeCenterY + 21} V100 H0 Z`} fill="url(#roamMapWater)" opacity="0.55" />
        <g opacity="0.74">
          {Array.from({ length: 11 }).map((_, index) => (
            <path
              key={`local-h-${index}`}
              d={`M-4 ${10 + index * 8} C18 ${12 + index * 8}, 37 ${8 + index * 8}, 58 ${10 + index * 8} S82 ${14 + index * 8}, 104 ${10 + index * 8}`}
              fill="none"
              stroke="#e5e7eb"
              strokeWidth="0.38"
            />
          ))}
          {Array.from({ length: 10 }).map((_, index) => (
            <path
              key={`local-v-${index}`}
              d={`M${6 + index * 10} -4 C${9 + index * 10} 18, ${4 + index * 10} 40, ${7 + index * 10} 64 S${12 + index * 10} 88, ${8 + index * 10} 104`}
              fill="none"
              stroke="#e5e7eb"
              strokeWidth="0.34"
            />
          ))}
        </g>
        <g filter="url(#roamMapSoft)">
          <path d="M-5 34 C16 32, 27 39, 42 36 S67 24, 86 29 101 35, 105 33" fill="none" stroke="#facc15" strokeWidth="4.2" strokeLinecap="round" />
          <path d="M-5 34 C16 32, 27 39, 42 36 S67 24, 86 29 101 35, 105 33" fill="none" stroke="#fff7ed" strokeWidth="2.3" strokeLinecap="round" />
          <path d="M3 76 C24 70, 35 78, 51 72 S73 58, 96 64" fill="none" stroke="#fb923c" strokeWidth="3.8" strokeLinecap="round" />
          <path d="M3 76 C24 70, 35 78, 51 72 S73 58, 96 64" fill="none" stroke="#fff7ed" strokeWidth="2" strokeLinecap="round" />
          <path d={`M0 ${routeCenterY} C20 ${routeCenterY - 8}, 34 ${routeCenterY + 10}, 50 ${routeCenterY} S76 ${routeCenterY - 11}, 100 ${routeCenterY - 1}`} fill="none" stroke="#22c55e" strokeWidth="1.4" strokeLinecap="round" />
          <path d={`M${Math.max(0, routeCenterX - 52)} 6 C${routeCenterX - 22} 25, ${routeCenterX + 2} 44, ${routeCenterX + 24} 64 S${routeCenterX + 42} 88, ${Math.min(100, routeCenterX + 54)} 98`} fill="none" stroke="#a855f7" strokeWidth="1.15" strokeLinecap="round" />
        </g>
        <g>
          {[
            [10, 16, 16, 12, "#eef2ff"],
            [36, 12, 20, 15, "#f1f5f9"],
            [68, 14, 18, 12, "#f1f5f9"],
            [12, 58, 17, 15, "#ecfdf5"],
            [43, 58, 20, 13, "#f8fafc"],
            [72, 58, 18, 16, "#eff6ff"],
          ].map(([x, y, width, height, fill], index) => (
            <rect
              key={`block-${index}`}
              x={x}
              y={y}
              width={width}
              height={height}
              rx="2.2"
              fill={fill as string}
              stroke="#dbe3ee"
              strokeWidth="0.35"
              opacity="0.82"
            />
          ))}
        </g>
        {routePath && <path d={routePath} fill="none" stroke="rgba(37,99,235,0.08)" strokeWidth="8" strokeLinecap="round" strokeLinejoin="round" />}
        <g>
          {stationPoints.map((point, index) => (
            <g key={`station-${point.block.id}`}>
              <circle cx={point.x} cy={point.y} r="1.2" fill="#ffffff" stroke="#22c55e" strokeWidth="0.45" />
              {index % 2 === 0 && (
                <text x={point.x + 1.8} y={point.y - 1.5} fontSize="2.1" fontWeight="700" fill="#16a34a">M{(index % 3) + 1}</text>
              )}
            </g>
          ))}
          {poiPoints.slice(0, 6).map((point, index) => (
            <circle key={`poi-dot-${point.block.id}`} cx={point.x + (index % 2 ? 4 : -4)} cy={point.y + (index % 3 - 1) * 4} r="0.9" fill="#93c5fd" opacity="0.45" />
          ))}
        </g>
      </svg>
    </div>
  );
}

function projectRouteBlueprint(routeBlocks: ItineraryBlock[], mapPois: ItineraryBlock[]) {
  const routeCoords = routeBlocks
    .map((block) => ({ block, coord: blockLngLat(block) }))
    .filter((item): item is { block: ItineraryBlock; coord: { lng: number; lat: number } } => item.coord !== null);
  const poiCoords = mapPois
    .slice(0, 12)
    .map((block) => ({ block, coord: blockLngLat(block) }))
    .filter((item): item is { block: ItineraryBlock; coord: { lng: number; lat: number } } => item.coord !== null);

  if (routeCoords.length >= 2) {
    const bounds = coordinateBounds(routeCoords.map((item) => item.coord));
    const route = spreadProjectedPoints(routeCoords.map((item) => ({
      block: item.block,
      ...projectCoord(item.coord, bounds, 8, 92, 14, 86),
    })), 7.5);
    const pois = spreadProjectedPoints(poiCoords.map((item) => ({
      block: item.block,
      ...projectCoord(item.coord, bounds, 5, 95, 10, 90),
    })), 6.2);
    return { route, pois };
  }

  const route = routeBlocks.map((block, index) => {
    const ratio = routeBlocks.length <= 1 ? 0.5 : index / (routeBlocks.length - 1);
    const rhythm = [58, 34, 55, 70, 42, 60, 30, 52, 72];
    return {
      block,
      x: 12 + ratio * 76,
      y: rhythm[index % rhythm.length],
    };
  });

  const pois = mapPois.slice(0, 12).map((block, index) => {
    const row = Math.floor(index / 6);
    const col = index % 6;
    const topRow = row % 2 === 0;
    return {
      block,
      x: clamp(11 + col * 15.5 + (topRow ? 0 : 7.5), 6, 94),
      y: topRow ? 17 + (index % 2) * 7 : 82 - (index % 2) * 7,
    };
  });

  return { route, pois };
}

function blockLngLat(block: ItineraryBlock) {
  const lng = toNumber(block.lng);
  const lat = toNumber(block.lat);
  if (lng === null || lat === null) return null;
  return { lng, lat };
}

function coordinateBounds(coords: Array<{ lng: number; lat: number }>) {
  const lngs = coords.map((coord) => coord.lng);
  const lats = coords.map((coord) => coord.lat);
  const minLng = Math.min(...lngs);
  const maxLng = Math.max(...lngs);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const lngPad = Math.max((maxLng - minLng) * 0.28, 0.006);
  const latPad = Math.max((maxLat - minLat) * 0.28, 0.006);
  return {
    minLng: minLng - lngPad,
    maxLng: maxLng + lngPad,
    minLat: minLat - latPad,
    maxLat: maxLat + latPad,
  };
}

function projectCoord(
  coord: { lng: number; lat: number },
  bounds: { minLng: number; maxLng: number; minLat: number; maxLat: number },
  minX: number,
  maxX: number,
  minY: number,
  maxY: number,
) {
  const xRatio = (coord.lng - bounds.minLng) / Math.max(bounds.maxLng - bounds.minLng, 0.000001);
  const yRatio = (bounds.maxLat - coord.lat) / Math.max(bounds.maxLat - bounds.minLat, 0.000001);
  return {
    x: clamp(minX + xRatio * (maxX - minX), minX, maxX),
    y: clamp(minY + yRatio * (maxY - minY), minY, maxY),
  };
}

function spreadProjectedPoints(points: ProjectedMapPoint[], minDistance: number) {
  const result = points.map((point) => ({ ...point }));
  for (let pass = 0; pass < 6; pass += 1) {
    for (let i = 0; i < result.length; i += 1) {
      for (let j = i + 1; j < result.length; j += 1) {
        const dx = result[j].x - result[i].x;
        const dy = result[j].y - result[i].y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
        if (dist >= minDistance) continue;
        const shift = (minDistance - dist) / 2;
        const ux = dx / dist;
        const uy = dy / dist;
        const fallbackAngle = ((i + j + pass) * 47 * Math.PI) / 180;
        const sx = Number.isFinite(ux) ? ux : Math.cos(fallbackAngle);
        const sy = Number.isFinite(uy) ? uy : Math.sin(fallbackAngle);
        result[i].x = clamp(result[i].x - sx * shift, 6, 94);
        result[i].y = clamp(result[i].y - sy * shift, 12, 88);
        result[j].x = clamp(result[j].x + sx * shift, 6, 94);
        result[j].y = clamp(result[j].y + sy * shift, 12, 88);
      }
    }
  }
  return result;
}

function makeSvgPath(points: Array<{ x: number; y: number }>) {
  if (!points.length) return "";
  if (points.length === 1) return `M${points[0].x} ${points[0].y}`;
  return points
    .map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
    .join(" ");
}

function filterNearbyPois(routeBlocks: ItineraryBlock[], mapPois: ItineraryBlock[]) {
  const routeIds = new Set(routeBlocks.map((block) => block.id));
  const routeCoords = routeBlocks
    .map((block) => ({ lng: toNumber(block.lng), lat: toNumber(block.lat) }))
    .filter((coord): coord is { lng: number; lat: number } => coord.lng !== null && coord.lat !== null);
  if (!routeCoords.length) return mapPois.filter((poi) => !routeIds.has(poi.id)).slice(0, 10);

  const lngs = routeCoords.map((coord) => coord.lng);
  const lats = routeCoords.map((coord) => coord.lat);
  const minLng = Math.min(...lngs) - 0.014;
  const maxLng = Math.max(...lngs) + 0.014;
  const minLat = Math.min(...lats) - 0.014;
  const maxLat = Math.max(...lats) + 0.014;
  const filtered = mapPois.filter((poi) => {
    const lng = toNumber(poi.lng);
    const lat = toNumber(poi.lat);
    return !routeIds.has(poi.id) && lng !== null && lat !== null && lng >= minLng && lng <= maxLng && lat >= minLat && lat <= maxLat;
  });
  return (filtered.length ? filtered : mapPois.filter((poi) => !routeIds.has(poi.id))).slice(0, 12);
}

function routeMarkerColor(index: number, isStart: boolean) {
  if (isStart) return "#0284c7";
  const colors = ["#2563eb", "#0891b2", "#7c3aed", "#ea580c", "#db2777", "#16a34a", "#0f766e", "#4f46e5"];
  return colors[index % colors.length];
}

function shortPlaceName(name: string) {
  const cleaned = (name || "").replace(/\([^)]*\)/g, "").replace(/（[^）]*）/g, "").trim();
  if (!cleaned) return name || "";
  return cleaned.length > 10 ? `${cleaned.slice(0, 10)}...` : cleaned;
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}
