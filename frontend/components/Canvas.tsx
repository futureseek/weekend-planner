"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { MouseEvent as ReactMouseEvent } from "react";
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
    dragHint: "坐标草图 · 点击地点",
    zoom: "缩放",
    reset: "复位",
    startAccess: "起点接入",
    checklist: "Checklist",
    dayChecklist: "当天执行清单",
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
    dragHint: "Coordinate sketch · click marker",
    zoom: "Zoom",
    reset: "Reset",
    startAccess: "Start access",
    checklist: "Checklist",
    dayChecklist: "Daily checklist",
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

function displayCategory(category: string | undefined, language: Language) {
  if (!category) return "";
  return language === "en" ? (CATEGORY_EN[category] || category) : category;
}

function displayTimeNote(note: string | undefined, language: Language) {
  if (!note) return "";
  return language === "en" ? (TIME_NOTE_EN[note] || note) : note;
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

  const selectPlan = (plan: Itinerary) => {
    setActivePlan(plan);
    setActiveDay(1);
    setSelectedId(null);
  };

  const selectDay = (dayIndex: number) => {
    setActiveDay(dayIndex);
    setSelectedId(null);
  };

  const ACTION_MESSAGES: Record<string, string> = {
    less_walking: "我不想走太多路，请帮我重新规划，选近一点的地点",
    lower_budget: "请帮我提高性价比，重新分配预算",
    less_queue: "我不想排队，请帮我重新规划，避开排队多的地方",
    replace_poi: "请帮我换掉行程中的餐厅",
  };

  const handleAdjust = async (action: string) => {
    const userMsg = ACTION_MESSAGES[action] || `请帮我调整行程：${action}`;
    setAdjusting(action);
    try {
      const data = await apiPost<{ message: string; reply: string; itinerary?: Itinerary; alternatives?: Itinerary[] }>(
        "/api/itinerary/adjust",
        { action, session_id: sessionId, payload: {} },
        { timeoutMs: 120000 }
      );
      if (data.itinerary) {
        data.itinerary.alternatives = data.alternatives || data.itinerary.alternatives || [];
        setActivePlan(data.itinerary);
        setActiveDay(1);
        setSelectedId(null);
        onItineraryUpdate?.(data.itinerary);
      }
      onAdjustResult?.(data.message || userMsg, data.reply, data.itinerary);
    } catch {
      onAdjustResult?.(userMsg, "调整失败，后端没有返回可用方案。请稍后重试。");
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
            aria-label="关闭路线面板"
          >
            ×
          </button>
        </div>

        <div className="mt-4 grid grid-cols-3 gap-2">
          <Stat label={text.totalDuration} value={`${activePlan.total_duration}min`} />
          <Stat label={text.totalCost} value={`¥${activePlan.total_price}`} />
          <Stat label={text.transferDistance} value={formatDistance(activePlan.total_distance, language)} />
        </div>

        <div className="mt-4 flex gap-2 overflow-x-auto pb-1">
          {plans.map((plan, index) => {
            const active = plan === activePlan || plan.plan_name === activePlan.plan_name;
            return (
              <button
                key={`${plan.plan_name || "plan"}-${index}`}
                onClick={() => selectPlan(plan)}
                className={`min-w-44 rounded-lg border px-3 py-2.5 text-left transition ${
                  active
                    ? "border-blue-500 bg-blue-50 text-blue-800 shadow-sm"
                    : "border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50"
                }`}
              >
                <div className="text-sm font-semibold">{displayPlanName(plan.plan_name, language, language === "en" ? `Option ${index + 1}` : `方案${index + 1}`)}</div>
                 <div className="mt-1 text-xs opacity-80">{formatDayCount(plan.days?.length || 1, language)} · {plan.total_duration}min · ¥{plan.total_price}</div>
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
                  <div className="mt-2 text-xs text-slate-500">¥{day.total_price} · {formatStopCount(day.blocks.length, language)}</div>
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
          />
          {activePlan.start_transfer && activeDay === 1 && (
            <StartTransfer transfer={activePlan.start_transfer} language={language} />
          )}
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

function StartTransfer({ transfer, language }: { transfer: Connection; language: Language }) {
  const text = CANVAS_TEXT[language];
  return (
    <div className="mb-4 rounded-lg border border-blue-100 bg-blue-50/70 px-4 py-3 text-sm text-slate-700 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-blue-600 px-2 py-0.5 text-xs font-semibold text-white">{text.startAccess}</span>
        <span className="font-semibold text-slate-950">{transfer.from_name || (language === "en" ? "Start" : "起点")}</span>
        <span className="text-slate-400">→</span>
        <span className="font-semibold text-slate-950">{transfer.to_name}</span>
        <span className="text-xs text-slate-500">{displayMode(transfer.mode, language)} · {transfer.distance} · {transfer.time}</span>
      </div>
    </div>
  );
}

function UpgradeSuggestions({ suggestions, language }: { suggestions: UpgradeSuggestion[]; language: Language }) {
  const text = CANVAS_TEXT[language];
  if (!suggestions.length) return null;
  return (
    <section className="mb-4 rounded-lg border border-amber-200 bg-amber-50/70 p-4 shadow-sm">
      <div className="mb-3 flex items-end justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.16em] text-amber-700">{text.suggestions}</div>
          <div className="mt-1 text-sm text-amber-900">{text.suggestionHint}</div>
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {suggestions.slice(0, 4).map((item, index) => {
          const summary = language === "en" ? (item.summary_en || item.summary) : item.summary;
          return (
            <article key={`${item.title}-${index}`} className="rounded-lg border border-amber-100 bg-white/90 p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h4 className="truncate text-sm font-semibold text-slate-950">{item.title}</h4>
                  <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-600">{summary}</p>
                </div>
                {item.estimated_cost ? (
                  <span className="shrink-0 rounded-full bg-amber-100 px-2 py-1 text-[11px] font-semibold text-amber-800">
                    {text.estimated} ¥{item.estimated_cost}
                  </span>
                ) : null}
              </div>
              <div className="mt-2 flex flex-wrap gap-1">
                {([item.category, ...(item.tags || [])].filter(Boolean) as string[]).slice(0, 4).map((tag) => (
                  <span key={tag} className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600">{tag}</span>
                ))}
              </div>
            </article>
          );
        })}
      </div>
    </section>
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
}: {
  day: ItineraryDay;
  mapPois: ItineraryBlock[];
  selectedId: string | null;
  selectedBlock?: ItineraryBlock;
  onSelect: (id: string | null) => void;
  language: Language;
  totalDays: number;
}) {
  const text = CANVAS_TEXT[language];
  const [zoomDelta, setZoomDelta] = useState(0);
  const [panPx, setPanPx] = useState({ x: 0, y: 0 });
  const dragRef = useRef<{ startX: number; startY: number; x: number; y: number } | null>(null);
  const routeBlocks = useMemo(() => day.blocks.filter((block) => !block.is_start), [day.blocks]);
  const routeBlockIds = useMemo(() => new Set(routeBlocks.map((block) => block.id)), [routeBlocks]);
  const routeConnections = useMemo(
    () => day.connections.filter((conn) => routeBlockIds.has(conn.from) && routeBlockIds.has(conn.to)),
    [day.connections, routeBlockIds],
  );
  const nearbyPois = useMemo(() => filterNearbyPois(routeBlocks, mapPois), [routeBlocks, mapPois]);
  const projected = useMemo(() => projectMapItems(routeBlocks, nearbyPois, zoomDelta), [routeBlocks, nearbyPois, zoomDelta]);
  const routeSegments = projected.route.slice(0, -1).map((point, index) => ({
    from: point,
    to: projected.route[index + 1],
    connection: routeConnections[index],
  }));
  const routeMarkerLabel = (index: number) => {
    const block = projected.route[index]?.block;
    if (!block) return String(index + 1);
    return String(index + 1);
  };

  useEffect(() => {
    setPanPx({ x: 0, y: 0 });
    setZoomDelta(0);
  }, [day.day_index, routeBlocks]);

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      if (!dragRef.current) return;
      setPanPx({
        x: dragRef.current.x + event.clientX - dragRef.current.startX,
        y: dragRef.current.y + event.clientY - dragRef.current.startY,
      });
    };
    const handleMouseUp = () => {
      dragRef.current = null;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, []);

  const startMapDrag = (event: ReactMouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    dragRef.current = { startX: event.clientX, startY: event.clientY, x: panPx.x, y: panPx.y };
    document.body.style.cursor = "grab";
    document.body.style.userSelect = "none";
  };

  return (
    <div className="mb-4 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">{text.mapView}</div>
          <h3 className="mt-1 text-lg font-semibold text-slate-950">
            {displayDayTitle(day, language, totalDays)}
            {totalDays > 1 && day.date_label ? ` · ${displayDateLabel(day.date_label, language)}` : ""}
          </h3>
        </div>
        <div className="rounded-lg bg-slate-50 px-3 py-2 text-right text-xs text-slate-500">
          <div>{day.start_time} - {day.end_time}</div>
          <div className="mt-1">{formatStopCount(day.blocks.length, language)} · {formatSegmentCount(day.connections.length, language)}</div>
        </div>
      </div>

      <div
        className="relative h-[440px] cursor-grab overflow-hidden bg-[#dcecf5] active:cursor-grabbing"
        onMouseDown={startMapDrag}
        onClick={() => onSelect(null)}
      >
        <AbstractRouteBackdrop />
        <div className="absolute inset-0 bg-gradient-to-b from-white/40 via-transparent to-slate-900/5" />
        <div
          className="absolute inset-0"
          style={{ transform: `translate(${panPx.x}px, ${panPx.y}px)` }}
        >
          <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
            {routeSegments.map((segment, index) => (
              <g key={`${segment.from.block.id}-${segment.to.block.id}`}>
                <line
                  x1={segment.from.x}
                  y1={segment.from.y}
                  x2={segment.to.x}
                  y2={segment.to.y}
                  stroke="rgba(255,255,255,0.95)"
                  strokeWidth="0.88"
                  strokeLinecap="round"
                />
                <line
                  x1={segment.from.x}
                  y1={segment.from.y}
                  x2={segment.to.x}
                  y2={segment.to.y}
                  stroke={segment.connection?.mode === "公共交通" || segment.connection?.mode === "public transit" ? "#2563eb" : "#0ea5e9"}
                  strokeWidth="0.32"
                  strokeLinecap="round"
                />
              </g>
            ))}
          </svg>

          {routeSegments.map((segment, index) => {
            const x = (segment.from.x + segment.to.x) / 2;
            const y = (segment.from.y + segment.to.y) / 2;
            const label = segment.connection
              ? `${displayMode(segment.connection.mode, language)} · ${segment.connection.time}`
              : (language === "en" ? `Transfer ${index + 1}` : `转场 ${index + 1}`);
            return (
              <div
                key={`${segment.from.block.id}-${segment.to.block.id}-label`}
                className="pointer-events-none absolute z-10 max-w-[138px] -translate-x-1/2 -translate-y-1/2 truncate rounded-full border border-slate-200 bg-white/90 px-2 py-0.5 text-[10px] font-medium text-slate-600 shadow-sm backdrop-blur"
                style={{ left: `${x}%`, top: `${y}%` }}
              >
                {label}
              </div>
            );
          })}
        </div>

        <div
          className="absolute left-4 top-4 z-20 flex items-center gap-2 rounded-full border border-white/80 bg-white/90 px-3 py-1.5 text-xs text-slate-600 shadow-sm backdrop-blur"
          onMouseDown={(event) => event.stopPropagation()}
        >
          <span className="inline-flex h-2.5 w-2.5 rounded-full bg-sky-500" /> {text.route}
          <span className="ml-2 inline-flex h-2.5 w-2.5 rounded-full bg-white ring-2 ring-slate-300" /> {text.nearbyPoi}
          <span className="ml-2 hidden text-slate-400 sm:inline">{text.dragHint}</span>
        </div>

        <div
          className="absolute inset-0"
          style={{ transform: `translate(${panPx.x}px, ${panPx.y}px)` }}
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
              className={`absolute z-10 flex h-8 w-8 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border bg-white text-xs shadow-lg transition hover:scale-110 ${
                active ? "border-blue-500 ring-4 ring-blue-100" : "border-white ring-2 ring-white/70"
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
            <button
              key={point.block.id}
              onClick={(event) => {
                event.stopPropagation();
                onSelect(active ? null : point.block.id);
              }}
              onMouseDown={(event) => event.stopPropagation()}
              className={`absolute z-20 flex h-8 w-8 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-2 text-xs font-bold text-white shadow-[0_10px_24px_rgba(15,23,42,0.22)] transition hover:scale-110 ${
                active ? "border-white ring-4 ring-blue-100" : "border-white ring-4 ring-white/80"
              }`}
              style={{ left: `${point.x}%`, top: `${point.y}%`, backgroundColor: markerColor }}
              title={point.block.name}
            >
              {routeMarkerLabel(index)}
            </button>
          );
        })}
        </div>

        <div
          className="absolute right-4 top-4 z-20 w-44 rounded-lg border border-white/80 bg-white/95 px-3 py-2 text-xs text-slate-600 shadow-sm backdrop-blur"
          onMouseDown={(event) => event.stopPropagation()}
          onClick={(event) => event.stopPropagation()}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium">{text.zoom}</span>
            <span className="font-mono text-[11px] text-slate-400">{projected.zoom.toFixed(1)}</span>
          </div>
          <input
            type="range"
            min={-2}
            max={3}
            step={0.05}
            value={zoomDelta}
            onChange={(event) => setZoomDelta(Number(event.target.value))}
            className="mt-2 w-full accent-blue-600"
            aria-label={text.zoom}
          />
          <button
            type="button"
            onClick={() => {
              setPanPx({ x: 0, y: 0 });
              setZoomDelta(0);
              onSelect(null);
            }}
            className="mt-2 w-full rounded-md border border-slate-200 px-2 py-1 text-[11px] font-semibold text-slate-600 transition hover:bg-slate-50"
          >
            {text.reset}
          </button>
        </div>

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
                  <span>{selectedBlock.duration}{text.minute}</span>
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
        {day.blocks.map((block, index) => {
          const style = getStyle(block.type);
          const connection = day.connections[index];
          const selected = selectedId === block.id;
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
                       <div className="mt-1 text-sm text-slate-500">{block.duration}min · ¥{block.price}</div>
                      {block.reason && <div className="mt-2 line-clamp-2 text-xs leading-5 text-slate-600">{block.reason}</div>}
                      {block.time_note && <div className="mt-1 text-xs text-blue-600">{displayTimeNote(block.time_note, language)}</div>}
                      <div className="mt-3 flex flex-wrap gap-1">
                        {(block.tags || []).slice(0, 4).map((tag) => (
                          <span key={tag} className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600">{tag}</span>
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
                    onClick={() => setOpenConnection(openConnection === `${connection.from}-${connection.to}` ? null : `${connection.from}-${connection.to}`)}
                    className="inline-flex rounded-full bg-white px-3 py-1.5 text-xs text-slate-500 shadow-sm ring-1 ring-slate-200 transition hover:bg-blue-50 hover:text-blue-700 hover:ring-blue-200"
                  >
                    {displayMode(connection.mode, language)} · {connection.distance} · {connection.time}
                  </button>
                  {openConnection === `${connection.from}-${connection.to}` && (
                    <div className="mt-2 max-w-xl rounded-lg border border-slate-200 bg-white p-3 text-xs leading-5 text-slate-600 shadow-sm">
                      <div className="font-semibold text-slate-900">
                        {connection.transit_detail?.summary || (language === "en" ? "Transfer estimate" : "转场估算")}
                      </div>
                      {connection.transit_detail?.segments?.length ? (
                        <ul className="mt-2 space-y-1">
                          {connection.transit_detail.segments.slice(0, 5).map((segment, idx) => (
                            <li key={`${segment}-${idx}`}>{segment}</li>
                          ))}
                        </ul>
                      ) : (
                        <p className="mt-1">
                          {language === "en"
                            ? "Detailed transit is not available yet. The current route uses distance and duration estimates."
                            : "暂未获取到公交换乘明细，当前展示为距离和时间估算。"}
                        </p>
                      )}
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

const MAP_W = 1200;
const MAP_H = 420;
const TILE_SIZE = 256;

function AbstractRouteBackdrop() {
  return (
    <div className="absolute inset-0 overflow-hidden bg-[#eef7fb]">
      <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(37,99,235,0.06)_1px,transparent_1px),linear-gradient(to_bottom,rgba(37,99,235,0.06)_1px,transparent_1px)] bg-[size:44px_44px]" />
      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 1200 420" preserveAspectRatio="none" aria-hidden>
        <rect x="0" y="296" width="1200" height="124" fill="rgba(125,211,252,0.28)" />
        <rect x="70" y="70" width="210" height="112" rx="18" fill="rgba(255,255,255,0.60)" stroke="rgba(226,232,240,0.9)" />
        <rect x="432" y="46" width="276" height="116" rx="22" fill="rgba(255,255,255,0.56)" stroke="rgba(226,232,240,0.9)" />
        <rect x="930" y="238" width="198" height="126" rx="24" fill="rgba(187,247,208,0.38)" stroke="rgba(134,239,172,0.55)" />
        <rect x="94" y="238" width="146" height="132" rx="28" fill="rgba(187,247,208,0.30)" stroke="rgba(134,239,172,0.42)" />
        <line x1="42" y1="248" x2="1162" y2="248" stroke="rgba(255,255,255,0.92)" strokeWidth="11" strokeLinecap="round" />
        <line x1="122" y1="338" x2="1104" y2="338" stroke="rgba(255,255,255,0.82)" strokeWidth="8" strokeLinecap="round" />
        <line x1="224" y1="0" x2="314" y2="420" stroke="rgba(255,255,255,0.74)" strokeWidth="8" strokeLinecap="round" />
        <line x1="706" y1="0" x2="662" y2="420" stroke="rgba(255,255,255,0.78)" strokeWidth="9" strokeLinecap="round" />
        <line x1="0" y1="128" x2="1200" y2="186" stroke="rgba(255,255,255,0.78)" strokeWidth="9" strokeLinecap="round" />
        <line x1="72" y1="84" x2="1092" y2="274" stroke="rgba(148,163,184,0.24)" strokeWidth="3" strokeDasharray="12 14" strokeLinecap="round" />
        {Array.from({ length: 9 }).map((_, index) => (
          <line
            key={index}
            x1={index * 140}
            y1="0"
            x2={index * 140 - 54}
            y2="420"
            stroke="rgba(37,99,235,0.08)"
            strokeWidth="1"
          />
        ))}
      </svg>
    </div>
  );
}

function filterNearbyPois(routeBlocks: ItineraryBlock[], mapPois: ItineraryBlock[]) {
  const routeCoords = routeBlocks
    .map((block) => ({ lng: toNumber(block.lng), lat: toNumber(block.lat) }))
    .filter((coord): coord is { lng: number; lat: number } => coord.lng !== null && coord.lat !== null);
  if (!routeCoords.length) return mapPois.slice(0, 18);

  const lngs = routeCoords.map((coord) => coord.lng);
  const lats = routeCoords.map((coord) => coord.lat);
  const minLng = Math.min(...lngs) - 0.025;
  const maxLng = Math.max(...lngs) + 0.025;
  const minLat = Math.min(...lats) - 0.025;
  const maxLat = Math.max(...lats) + 0.025;
  const filtered = mapPois.filter((poi) => {
    const lng = toNumber(poi.lng);
    const lat = toNumber(poi.lat);
    return lng !== null && lat !== null && lng >= minLng && lng <= maxLng && lat >= minLat && lat <= maxLat;
  });
  return (filtered.length ? filtered : mapPois).slice(0, 22);
}

function projectMapItems(routeBlocks: ItineraryBlock[], mapPois: ItineraryBlock[], zoomDelta = 0) {
  const routeCoords = toCoordItems(routeBlocks);
  const poiCoords = toCoordItems(mapPois);
  const allCoords = [...routeCoords, ...poiCoords];

  if (!allCoords.length) {
    return {
      center: null,
      zoom: 13,
      route: spreadProjectedPoints(routeBlocks.map((block, index) => ({ block, x: 14 + (index % 4) * 24, y: 22 + Math.floor(index / 4) * 28 })), 6.2),
      pois: [],
    };
  }

  const lngs = allCoords.map((item) => item.lng);
  const lats = allCoords.map((item) => item.lat);
  const minLng = Math.min(...lngs);
  const maxLng = Math.max(...lngs);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const center = { lng: (minLng + maxLng) / 2, lat: (minLat + maxLat) / 2 };
  const zoom = Math.min(17, Math.max(10, chooseZoom(maxLng - minLng, maxLat - minLat) + zoomDelta));
  const centerWorld = lngLatToWorld(center.lng, center.lat, zoom);

  const project = (item: { block: ItineraryBlock; lng: number; lat: number }) => {
    const world = lngLatToWorld(item.lng, item.lat, zoom);
    return {
      block: item.block,
      x: clamp(((world.x - centerWorld.x + MAP_W / 2) / MAP_W) * 100, 4, 96),
      y: clamp(((world.y - centerWorld.y + MAP_H / 2) / MAP_H) * 100, 7, 93),
    };
  };

  return {
    center,
    zoom,
    route: spreadProjectedPoints(routeCoords.map(project), 6.2),
    pois: spreadProjectedPoints(poiCoords.map(project), 4.6),
  };
}

function spreadProjectedPoints<T extends { block: ItineraryBlock; x: number; y: number }>(points: T[], minDistance: number): T[] {
  const adjusted: T[] = [];
  for (const point of points) {
    let x = point.x;
    let y = point.y;
    for (let attempt = 0; attempt < 7; attempt += 1) {
      const conflict = adjusted.find((item) => Math.hypot(item.x - x, item.y - y) < minDistance);
      if (!conflict) break;
      const angle = (adjusted.length + attempt * 2.15) * 1.618;
      const push = minDistance + attempt * 1.2;
      x = clamp(point.x + Math.cos(angle) * push, 4, 96);
      y = clamp(point.y + Math.sin(angle) * push, 7, 93);
    }
    adjusted.push({ ...point, x, y });
  }
  return adjusted;
}

function routeMarkerColor(index: number, isStart: boolean) {
  if (isStart) return "#0284c7";
  const colors = ["#2563eb", "#0891b2", "#7c3aed", "#ea580c", "#db2777", "#16a34a", "#0f766e", "#4f46e5"];
  return colors[index % colors.length];
}

function toCoordItems(blocks: ItineraryBlock[]) {
  return blocks
    .map((block) => ({ block, lng: toNumber(block.lng), lat: toNumber(block.lat) }))
    .filter((item): item is { block: ItineraryBlock; lng: number; lat: number } => item.lng !== null && item.lat !== null);
}

function chooseZoom(lngRange: number, latRange: number) {
  const span = Math.max(Math.abs(lngRange), Math.abs(latRange));
  if (span > 0.18) return 11;
  if (span > 0.08) return 12;
  if (span > 0.04) return 13;
  if (span > 0.018) return 14;
  return 15;
}

function lngLatToWorld(lng: number, lat: number, zoom: number) {
  const sinLat = Math.sin((Math.max(-85, Math.min(85, lat)) * Math.PI) / 180);
  const size = TILE_SIZE * 2 ** zoom;
  return {
    x: ((lng + 180) / 360) * size,
    y: (0.5 - Math.log((1 + sinLat) / (1 - sinLat)) / (4 * Math.PI)) * size,
  };
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}
