"use client";

import { useEffect, useMemo, useState } from "react";
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
  day_index?: number;
  start_time?: string;
  end_time?: string;
  time_note?: string;
}

export interface Connection {
  from: string;
  to: string;
  distance: string;
  time: string;
  mode?: string;
  day_index?: number;
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
  guide_signals?: {
    strategy?: string[];
    snippets?: string[];
    positive_keywords?: string[];
    avoid_keywords?: string[];
  };
}

const TYPE_STYLES: Record<string, { bg: string; text: string; border: string; accent: string }> = {
  cafe: { bg: "bg-amber-50", text: "text-amber-800", border: "border-amber-200", accent: "bg-amber-400" },
  food: { bg: "bg-orange-50", text: "text-orange-800", border: "border-orange-200", accent: "bg-orange-400" },
  restaurant: { bg: "bg-orange-50", text: "text-orange-800", border: "border-orange-200", accent: "bg-orange-400" },
  scenic: { bg: "bg-teal-50", text: "text-teal-800", border: "border-teal-200", accent: "bg-teal-400" },
  exhibition: { bg: "bg-sky-50", text: "text-sky-800", border: "border-sky-200", accent: "bg-sky-400" },
  park: { bg: "bg-emerald-50", text: "text-emerald-800", border: "border-emerald-200", accent: "bg-emerald-400" },
  shopping: { bg: "bg-rose-50", text: "text-rose-800", border: "border-rose-200", accent: "bg-rose-400" },
  entertainment: { bg: "bg-violet-50", text: "text-violet-800", border: "border-violet-200", accent: "bg-violet-400" },
};

const DEFAULT_STYLE = { bg: "bg-slate-50", text: "text-slate-700", border: "border-slate-200", accent: "bg-slate-400" };

function getStyle(type?: string) {
  return type ? TYPE_STYLES[type.toLowerCase()] || DEFAULT_STYLE : DEFAULT_STYLE;
}

function formatDistance(distance?: number) {
  if (!distance) return "未知";
  return distance < 1000 ? `${distance}m` : `${(distance / 1000).toFixed(1)}km`;
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

interface CanvasProps {
  itinerary: Itinerary | null;
  onClose: () => void;
  onItineraryUpdate?: (itinerary: Itinerary) => void;
  onAdjustResult?: (userMsg: string, reply: string, itinerary?: Itinerary) => void;
  sessionId: string;
}

export default function Canvas({ itinerary, onClose, onItineraryUpdate, onAdjustResult, sessionId }: CanvasProps) {
  const [activePlan, setActivePlan] = useState<Itinerary | null>(itinerary);
  const [activeDay, setActiveDay] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [adjusting, setAdjusting] = useState<string | null>(null);

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
  const selectedBlock = activePlan.blocks.find((block) => block.id === selectedId);
  const events = activePlan.event_suggestions || [];

  const selectPlan = (plan: Itinerary) => {
    setActivePlan(plan);
    setActiveDay(1);
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
        { action, session_id: sessionId, payload: {} }
      );
      if (data.itinerary) {
        data.itinerary.alternatives = data.alternatives || data.itinerary.alternatives || [];
        setActivePlan(data.itinerary);
        setActiveDay(1);
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
    <div className="flex h-full flex-col bg-[#f6f8fb]">
      <div className="shrink-0 border-b border-slate-200 bg-white px-5 py-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">路线工作台</div>
            <h2 className="mt-1 text-xl font-semibold text-slate-950">{activePlan.plan_name || "路线方案"}</h2>
            <p className="mt-1 text-xs text-slate-500">{activePlan.time_plan?.note || "按可用时间拆分行程"}</p>
          </div>
          <button
            onClick={onClose}
            className="h-8 w-8 rounded-lg border border-slate-200 text-slate-400 hover:bg-slate-50 hover:text-slate-700"
            aria-label="关闭路线面板"
          >
            ×
          </button>
        </div>

        <div className="mt-4 grid grid-cols-3 gap-2">
          <Stat label="总时长" value={`${activePlan.total_duration}min`} />
          <Stat label="预计花费" value={`¥${activePlan.total_price}`} />
          <Stat label="转场距离" value={formatDistance(activePlan.total_distance)} />
        </div>

        <div className="mt-4 flex gap-2 overflow-x-auto pb-1">
          {plans.map((plan, index) => {
            const active = plan === activePlan || plan.plan_name === activePlan.plan_name;
            return (
              <button
                key={`${plan.plan_name || "plan"}-${index}`}
                onClick={() => selectPlan(plan)}
                className={`min-w-40 rounded-lg border px-3 py-2 text-left transition ${
                  active
                    ? "border-blue-500 bg-blue-50 text-blue-800"
                    : "border-slate-200 bg-white text-slate-700 hover:border-slate-300"
                }`}
              >
                <div className="text-sm font-semibold">{plan.plan_name || `方案${index + 1}`}</div>
                <div className="mt-1 text-xs opacity-80">{plan.days?.length || 1}天 · {plan.total_duration}min · ¥{plan.total_price}</div>
              </button>
            );
          })}
        </div>

        {events.length > 0 && (
          <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
            <div className="text-xs font-semibold text-amber-900">近期活动信号</div>
            <div className="mt-2 flex gap-2 overflow-x-auto">
              {events.slice(0, 4).map((event, index) => (
                <a
                  key={`${event.title}-${index}`}
                  href={event.url || "#"}
                  target="_blank"
                  rel="noreferrer"
                  className="min-w-56 rounded-md bg-white px-3 py-2 text-xs text-amber-950 shadow-sm"
                >
                  <div className="line-clamp-1 font-semibold">{event.title}</div>
                  <div className="mt-1 line-clamp-2 text-amber-800">{event.summary}</div>
                </a>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-[150px_1fr]">
        <aside className="border-r border-slate-200 bg-white p-3">
          <div className="space-y-2">
            {days.map((day) => {
              const active = day.day_index === currentDay.day_index;
              return (
                <button
                  key={day.day_index}
                  onClick={() => setActiveDay(day.day_index)}
                  className={`w-full rounded-lg border px-3 py-3 text-left transition ${
                    active ? "border-blue-500 bg-blue-50 text-blue-800" : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                  }`}
                >
                  <div className="text-sm font-semibold">{day.title}</div>
                  <div className="mt-1 text-xs">{day.date_label}</div>
                  <div className="mt-2 text-xs text-slate-500">¥{day.total_price} · {day.blocks.length}站</div>
                </button>
              );
            })}
          </div>
        </aside>

        <div className="min-h-0 overflow-auto p-5">
          <div className="mb-4 rounded-lg border border-slate-200 bg-white p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="font-semibold text-slate-950">{currentDay.title} · {currentDay.date_label}</h3>
                <p className="mt-1 text-sm text-slate-500">{currentDay.start_time} - {currentDay.end_time} · {currentDay.total_duration}min · ¥{currentDay.total_price}</p>
              </div>
              <div className="flex -space-x-2">
                {currentDay.blocks.slice(0, 5).map((block) => {
                  const style = getStyle(block.type);
                  return (
                    <div key={block.id} className={`flex h-8 w-8 items-center justify-center rounded-full border-2 border-white ${style.bg} ${style.text} text-xs`}>
                      {block.icon}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          <RouteOverview day={currentDay} onSelect={setSelectedId} selectedId={selectedId} />

          <div className="relative space-y-4">
            <div className="absolute bottom-8 left-[76px] top-8 w-px bg-slate-200" />
            {currentDay.blocks.map((block, index) => {
              const style = getStyle(block.type);
              const connection = currentDay.connections[index];
              const selected = selectedId === block.id;
              return (
                <div key={block.id}>
                  <button
                    onClick={() => setSelectedId(selected ? null : block.id)}
                    className={`relative grid w-full grid-cols-[110px_1fr] gap-4 rounded-lg border bg-white p-4 text-left shadow-sm transition hover:shadow-md ${
                      selected ? "border-blue-500 ring-2 ring-blue-100" : style.border
                    }`}
                  >
                    <div className="text-sm">
                      <div className="font-semibold text-slate-950">{block.start_time || "--:--"}</div>
                      <div className="mt-1 text-xs text-slate-500">{block.end_time || ""}</div>
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-start gap-3">
                        <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${style.bg} ${style.text}`}>
                          {block.icon}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-semibold text-slate-400">{String(index + 1).padStart(2, "0")}</span>
                            <h4 className="truncate font-semibold text-slate-950">{block.name}</h4>
                          </div>
                          <div className="mt-1 text-sm text-slate-500">{block.duration}min · ¥{block.price}</div>
                          {block.time_note && (
                            <div className="mt-1 text-xs text-blue-600">{block.time_note}</div>
                          )}
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
                    <div className="ml-[126px] py-2 text-xs text-slate-500">
                      {connection.mode || "步行"} · {connection.distance} · {connection.time}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {selectedBlock && (
        <div className="shrink-0 border-t border-slate-200 bg-white p-4">
          <div className="flex items-start gap-3">
            <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${getStyle(selectedBlock.type).bg} ${getStyle(selectedBlock.type).text}`}>
              {selectedBlock.icon}
            </div>
            <div className="min-w-0">
              <h3 className="font-semibold text-slate-950">{selectedBlock.name}</h3>
              <p className="mt-1 text-sm text-slate-600">{selectedBlock.reason || selectedBlock.recommendation || selectedBlock.address}</p>
              <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-500">
                <span>{selectedBlock.duration} 分钟</span>
                <span>合计 ¥{selectedBlock.price}{selectedBlock.unit_price !== undefined ? ` · 人均 ¥${selectedBlock.unit_price}` : ""}</span>
                {selectedBlock.rating ? <span>评分 {selectedBlock.rating}</span> : null}
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="shrink-0 border-t border-slate-200 bg-white px-4 py-3">
        <div className="flex gap-2 overflow-x-auto">
          {[
            { key: "less_walking", label: "少走路" },
            { key: "lower_budget", label: "性价比" },
            { key: "less_queue", label: "少排队" },
            { key: "replace_poi", label: "换餐厅" },
          ].map((btn) => (
            <button
              key={btn.key}
              onClick={() => handleAdjust(btn.key)}
              disabled={adjusting !== null}
              className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                adjusting === btn.key
                  ? "border-blue-300 bg-blue-50 text-blue-700"
                  : "border-slate-200 text-slate-600 hover:border-slate-300 hover:bg-slate-50"
              } disabled:cursor-not-allowed disabled:opacity-60`}
            >
              {adjusting === btn.key ? "调整中..." : btn.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-1 font-semibold text-slate-950">{value}</div>
    </div>
  );
}

function RouteOverview({
  day,
  onSelect,
  selectedId,
}: {
  day: ItineraryDay;
  onSelect: (id: string | null) => void;
  selectedId: string | null;
}) {
  return (
    <div className="mb-4 rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">route map</div>
          <h3 className="mt-1 font-semibold text-slate-950">当天路线结构</h3>
        </div>
        <div className="text-xs text-slate-500">{day.blocks.length}站 · {day.connections.length}段转场</div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {day.blocks.map((block, index) => {
          const style = getStyle(block.type);
          const connection = day.connections[index];
          const active = selectedId === block.id;
          return (
            <button
              key={block.id}
              onClick={() => onSelect(active ? null : block.id)}
              className={`relative min-h-[120px] rounded-lg border p-3 text-left transition hover:shadow-md ${
                active ? "border-blue-500 bg-blue-50 ring-2 ring-blue-100" : `${style.border} ${style.bg}`
              }`}
            >
              <div className="flex items-start gap-3">
                <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-white ${style.text} shadow-sm`}>
                  {block.icon}
                </div>
                <div className="min-w-0">
                  <div className="text-xs font-semibold text-slate-500">{block.start_time} - {block.end_time}</div>
                  <div className="mt-1 line-clamp-2 font-semibold text-slate-950">{block.name}</div>
                  <div className="mt-1 text-xs text-slate-600">{block.duration}min · ¥{block.price}</div>
                  {block.time_note && <div className="mt-1 text-[11px] text-blue-600">{block.time_note}</div>}
                </div>
              </div>
              {connection && (
                <div className="mt-3 rounded-md border border-white/70 bg-white/80 px-2 py-1 text-xs text-slate-600">
                  下一站：{connection.mode || "步行"} · {connection.distance} · {connection.time}
                </div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
