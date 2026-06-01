"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { MouseEvent as ReactMouseEvent } from "react";
import { Itinerary } from "./Canvas";
import MarkdownMessage from "./MarkdownMessage";
import { apiPost } from "@/lib/api";

interface Message {
  role: "user" | "assistant";
  content: string;
  itinerary?: Itinerary;
}

const LOADING_TEXTS = [
  "解析城市、时间和预算",
  "检索 POI 和评价线索",
  "计算转场距离和路线顺序",
  "拆分多日行程和备选方案",
];

const EXAMPLE_PROMPTS = [
  "广州，2人，预算2000，玩5天，想吃好一点，也看看近期演出或市集",
  "上海，6.1-6.3，2人，预算2000，喜欢逛街和热闹的地方",
  "杭州，周六一天，2人，想爬山和喝咖啡，别太累",
  "成都，周末，3人，预算900，想打游戏、吃火锅、逛夜市",
  "周末一天，预算500，少排队，少走路，想逛吃",
];

interface LocationInfo {
  location: string;
  formatted_address?: string;
  city?: string;
  district?: string;
  adcode?: string;
}

const KNOWN_CITY_PATTERN =
  /(北京|上海|广州|深圳|杭州|成都|南京|苏州|重庆|武汉|西安|厦门|天津|长沙|青岛|大连|宁波|无锡|合肥|福州|南昌|济南|郑州|昆明|贵阳|南宁|海口|三亚|哈尔滨|沈阳|长春|大理|丽江|桂林|张家界|黄山|景德镇|泉州|扬州|洛阳|开封|威海|烟台|绍兴|嘉兴|温州|佛山|珠海|潮州|汕头|拉萨|喀什|乌鲁木齐|guangzhou|shanghai|beijing|shenzhen|chengdu|hangzhou|xian|xi'an|nanjing|suzhou|chongqing|wuhan|xiamen)/i;

function formatLocationLabel(info: LocationInfo) {
  const city = typeof info.city === "string" ? info.city.replace(/市$/, "") : "";
  const district = typeof info.district === "string" ? info.district.replace(/区$/, "") : "";
  if (city && district && city !== district) return `${city}${district}`;
  if (city || district) return city || district;
  if (info.formatted_address) return info.formatted_address.replace(/^(中国|中华人民共和国)/, "");
  return "当前位置附近";
}

function hasLocationInText(text: string) {
  if (!text.trim()) return false;
  return (
    /当前位置|从.{1,18}(出发|开始)|在.{1,14}(玩|游|逛|旅行|旅游)/.test(text) ||
    KNOWN_CITY_PATTERN.test(text) ||
    /[\u4e00-\u9fa5]{2,12}(市|区|县|州|镇|乡|旗|盟)/.test(text)
  );
}

interface ChatProps {
  sessionId: string;
  onItinerary: (itinerary: Itinerary | null) => void;
  onReady?: (
    sendMessage: (text: string) => void,
    addExternalMessage: (userMsg: string, reply: string, itinerary?: Itinerary) => void
  ) => void;
}

export default function Chat({ sessionId, onItinerary, onReady }: ChatProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingTextIndex, setLoadingTextIndex] = useState(0);
  const [oneShotLocation, setOneShotLocation] = useState<LocationInfo | null>(null);
  const [pendingLocation, setPendingLocation] = useState<LocationInfo | null>(null);
  const [geoStatus, setGeoStatus] = useState("可使用当前位置");
  const [composerHeight, setComposerHeight] = useState(220);
  const [loadingPlanIndex, setLoadingPlanIndex] = useState<number | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const resizeRef = useRef<{ startY: number; startHeight: number } | null>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loadingTextIndex]);

  useEffect(() => {
    if (!loading) {
      setLoadingTextIndex(0);
      return;
    }
    const timer = setInterval(() => {
      setLoadingTextIndex((prev) => (prev + 1) % LOADING_TEXTS.length);
    }, 1500);
    return () => clearInterval(timer);
  }, [loading]);

  useEffect(() => {
    if (!("geolocation" in navigator)) setGeoStatus("浏览器不支持定位");
  }, []);

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      if (!resizeRef.current) return;
      const delta = resizeRef.current.startY - event.clientY;
      setComposerHeight(Math.min(380, Math.max(170, resizeRef.current.startHeight + delta)));
    };
    const handleMouseUp = () => {
      resizeRef.current = null;
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

  const addExternalMessage = (userMsg: string, reply: string, itinerary?: Itinerary) => {
    setMessages((prev) => [
      ...prev,
      { role: "user", content: userMsg },
      { role: "assistant", content: reply, itinerary },
    ]);
  };

  const sendText = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || loading) return;

    setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
    setLoading(true);

    try {
      const locationForThisSend = oneShotLocation;
      const shouldUseOneShotLocation = locationForThisSend
        && !trimmed.includes("当前位置:")
        && trimmed.includes(formatLocationLabel(locationForThisSend));
      const enrichedText = shouldUseOneShotLocation
        ? `当前位置:${locationForThisSend.location}，${formatLocationLabel(locationForThisSend)}，${trimmed}`
        : trimmed;
      const data = await apiPost<{ reply: string; itinerary?: Itinerary; alternatives?: Itinerary[] }>(
        "/api/chat",
        { message: enrichedText, session_id: sessionId }
      );

      if (data.itinerary) {
        data.itinerary.alternatives = data.alternatives || data.itinerary.alternatives || [];
        onItinerary(data.itinerary);
      }

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.reply || "已生成路线，请查看右侧方案。", itinerary: data.itinerary },
      ]);
    } catch (error) {
      const detail = error instanceof Error && error.message ? `（${error.message}）` : "";
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `后端接口没有返回可用结果${detail}。请确认服务已启动后重试。` },
      ]);
    } finally {
      setLoading(false);
      if (oneShotLocation) {
        setOneShotLocation(null);
        setGeoStatus("可使用当前位置");
      }
    }
  }, [loading, oneShotLocation, onItinerary, sessionId]);

  useEffect(() => {
    onReady?.(sendText, addExternalMessage);
  }, [onReady, sendText]);

  const sendMessage = async () => {
    const text = input;
    setInput("");
    await sendText(text);
  };

  const suggestionPrompts = useMemo(() => {
    return EXAMPLE_PROMPTS;
  }, []);

  const requestCurrentLocation = () => {
    if (!("geolocation" in navigator)) {
      setGeoStatus("浏览器不支持定位");
      return;
    }
    setGeoStatus("正在定位...");
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const location = `${pos.coords.longitude.toFixed(6)},${pos.coords.latitude.toFixed(6)}`;
        try {
          const data = await apiPost<Omit<LocationInfo, "location"> & { location?: string }>("/api/location/reverse", { location });
          setPendingLocation({ ...data, location: data.location || location });
          setGeoStatus("请确认当前位置");
        } catch {
          setPendingLocation({ location });
          setGeoStatus("请确认当前位置");
        }
      },
      () => setGeoStatus("定位失败，可直接输入城市/区域"),
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 5 * 60 * 1000 }
    );
  };

  const confirmCurrentLocation = () => {
    if (!pendingLocation) return;
    const label = formatLocationLabel(pendingLocation);
    setOneShotLocation(pendingLocation);
    setInput((prev) => {
      const trimmed = prev.trim();
      if (!trimmed) return `从${label}出发，`;
      if (hasLocationInText(trimmed)) return trimmed;
      return `从${label}出发，${trimmed}`;
    });
    setPendingLocation(null);
    setGeoStatus(`已加入本次输入：${label}`);
  };

  const detectedFields = useMemo(() => {
    const text = input.trim();
    const chips = [];
    if (hasLocationInText(text)) chips.push("位置√");
    if (/\d{1,2}\s*(天|days?)|周末|周六|周日|today|tomorrow|weekend/i.test(text)) chips.push("时间√");
    if (/预算|budget|¥|rmb|cny|\d{2,6}\s*(元|块)/i.test(text)) chips.push("预算√");
    if (/\d{1,2}\s*(人|位|个人|people|pax)/i.test(text)) chips.push("人数√");
    if (/吃|咖啡|逛|展|拍照|亲子|少排队|避雷|爬山|徒步|户外|游戏|电竞|桌游|密室|food|coffee|shopping|museum|photo|hiking|game/i.test(text)) chips.push("偏好√");
    return chips;
  }, [input]);

  const startComposerResize = (event: ReactMouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    resizeRef.current = { startY: event.clientY, startHeight: composerHeight };
    document.body.style.cursor = "ns-resize";
    document.body.style.userSelect = "none";
  };

  const reloadItinerary = (index: number, itinerary: Itinerary) => {
    setLoadingPlanIndex(index);
    window.setTimeout(() => {
      onItinerary(itinerary);
      setLoadingPlanIndex(null);
    }, 180);
  };

  return (
    <div className="flex h-full flex-col bg-[#f5f7fb]">
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="mx-auto flex min-h-full w-full max-w-7xl flex-col gap-5">
          {messages.length === 0 && (
            <div className="grid flex-1 content-start gap-4 py-3">
              <section className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
                <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="text-sm font-semibold text-blue-700">Roam 漫游</div>
                      <h2 className="mt-2 max-w-2xl text-2xl font-semibold text-slate-950">把多个地点排成可以直接执行的路线</h2>
                      <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
                        底部写清城市、日期、人数、预算和偏好后，Roam 会组合 POI、评价线索、转场距离、近期活动和人群策略，生成可切换的多方案行程。
                      </p>
                    </div>
                    <div className="hidden rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-right lg:block">
                      <div className="text-xs text-blue-600">当前模式</div>
                      <div className="mt-1 text-sm font-semibold text-blue-800">多目标路线规划</div>
                    </div>
                  </div>

                  <div className="mt-5 grid gap-3 lg:grid-cols-[1fr_1fr_1fr]">
                    {[
                      ["01", "理解约束", "城市/区域、天数、预算、人数、偏好"],
                      ["02", "筛选地点", "高德 POI、评价摘要、活动信号和攻略线索"],
                      ["03", "生成方案", "按天拆分、错峰餐饮、少走路/性价比备选"],
                    ].map(([step, title, desc]) => (
                      <div key={step} className="border-l-2 border-slate-200 py-1 pl-3">
                        <div className="text-xs font-semibold text-slate-400">{step}</div>
                        <div className="mt-2 text-sm font-semibold text-slate-950">{title}</div>
                        <div className="mt-2 text-xs leading-5 text-slate-600">{desc}</div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">strategy engine</div>
                  <h3 className="mt-2 text-base font-semibold text-slate-950">不同人群，不同节奏</h3>
                  <div className="mt-4 space-y-3">
                    {[
                      ["户外体力型", "爬山/徒步放上午，下午安排补给和轻松点。", "bg-emerald-50 text-emerald-700 border-emerald-100"],
                      ["商圈逛吃型", "下午到傍晚逛街，晚餐和夜景接在同片区。", "bg-rose-50 text-rose-700 border-rose-100"],
                      ["游戏娱乐型", "电竞、密室、桌游放下午或晚间，不硬塞景点。", "bg-violet-50 text-violet-700 border-violet-100"],
                      ["亲子轻松型", "减少转场和排队，上午公园/展馆，下午留休息。", "bg-amber-50 text-amber-700 border-amber-100"],
                    ].map(([title, desc, style]) => (
                      <div key={title} className={`border-l-4 py-1 pl-3 ${style}`}>
                        <div className="text-sm font-semibold">{title}</div>
                        <div className="mt-1 text-xs leading-5 opacity-90">{desc}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </section>

              <section className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
                <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">route sandbox</div>
                      <h3 className="mt-2 text-base font-semibold text-slate-950">生成后会变成可操作路线板</h3>
                    </div>
                    <div className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">多方案切换</div>
                  </div>
                  <div className="mt-5 grid gap-3 sm:grid-cols-3">
                    {[
                      ["Day 1", "城市核心", "上午景点 · 午餐 · 下午茶"],
                      ["Day 2", "兴趣深挖", "户外/游戏/逛街按偏好换骨架"],
                      ["Day N", "余量调整", "活动、市集、少走路方案"],
                    ].map(([day, title, desc]) => (
                      <div key={day} className="border-l-2 border-slate-200 py-1 pl-3">
                        <div className="text-xs font-semibold text-blue-700">{day}</div>
                        <div className="mt-2 text-sm font-semibold text-slate-950">{title}</div>
                        <div className="mt-2 text-xs leading-5 text-slate-600">{desc}</div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">decision signals</div>
                  <h3 className="mt-2 text-base font-semibold text-slate-950">Roam 会在生成时同时权衡</h3>
                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    {[
                      ["预算利用", "预算充足时不会过度省钱，会加入更有价值的餐饮、体验和夜间活动。"],
                      ["餐饮时间窗", "早茶、午餐、下午茶、晚餐分时段安排，避免 10 点吃火锅。"],
                      ["全国覆盖", "优先按城市/区域和坐标查高德 POI，缓存只做兜底。"],
                      ["可继续调整", "右侧方案可要求少排队、少走路、换餐厅或提高性价比。"],
                    ].map(([title, desc]) => (
                      <div key={title} className="border-l-2 border-slate-200 py-1 pl-3">
                        <div className="text-sm font-semibold text-slate-950">{title}</div>
                        <div className="mt-1 text-xs leading-5 text-slate-600">{desc}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </section>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[86%] rounded-lg px-4 py-3 shadow-sm ${
                  msg.role === "user"
                    ? "bg-blue-600 text-white"
                    : "border border-slate-200 bg-white text-slate-800"
                }`}
              >
                {msg.role === "assistant" ? (
                  <>
                    <MarkdownMessage content={msg.content} />
                    {msg.itinerary && (
                      <button
                        onClick={() => reloadItinerary(i, msg.itinerary as Itinerary)}
                        disabled={loadingPlanIndex === i}
                        className="mt-3 rounded-lg border border-blue-200 px-3 py-1.5 text-xs font-semibold text-blue-700 hover:bg-blue-50"
                      >
                        {loadingPlanIndex === i ? "加载中..." : "重新加载到右侧方案"}
                      </button>
                    )}
                  </>
                ) : (
                  <p className="whitespace-pre-wrap text-[15px] leading-7">{msg.content}</p>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600 shadow-sm">
                <span className="mr-2 inline-block h-2 w-2 animate-pulse rounded-full bg-blue-500" />
                {LOADING_TEXTS[loadingTextIndex]}
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      <div className="relative border-t border-slate-200 bg-white/95 px-6 py-4 shadow-[0_-8px_24px_rgba(15,23,42,0.04)]">
        <div
          onMouseDown={startComposerResize}
          className="absolute left-0 right-0 top-0 h-3 cursor-ns-resize"
          aria-label="拖拽调整输入面板高度"
        />
        <div
          className="mx-auto flex w-full max-w-7xl flex-col rounded-lg border border-slate-200 bg-white p-4 shadow-sm focus-within:border-blue-400 focus-within:ring-2 focus-within:ring-blue-100"
          style={{ height: composerHeight }}
        >
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div>
              <label htmlFor="travel-requirement" className="text-sm font-semibold text-slate-950">
                出行需求
              </label>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {detectedFields.length ? detectedFields.map((chip) => (
                  <span key={chip} className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700">
                    {chip}
                  </span>
                )) : <span className="text-xs text-slate-500">{geoStatus}</span>}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={requestCurrentLocation}
                type="button"
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700"
              >
                当前位置
              </button>
              <span className="text-xs text-slate-400">Enter 发送，Shift + Enter 换行</span>
            </div>
          </div>
          <div className="flex min-h-0 flex-1 gap-3">
            <textarea
              id="travel-requirement"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  sendMessage();
                }
              }}
              placeholder=""
              className="min-h-0 flex-1 resize-none border-0 bg-transparent text-[15px] leading-7 text-slate-900 outline-none placeholder:text-slate-400"
              disabled={loading}
            />
            <button
              onClick={sendMessage}
              disabled={loading || !input.trim()}
              className="h-12 self-end rounded-lg bg-blue-600 px-5 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              发送
            </button>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {suggestionPrompts.slice(0, 5).map((prompt) => (
              <button
                key={prompt}
                onClick={() => {
                  setInput(prompt);
                  setOneShotLocation(null);
                  setGeoStatus("可使用当前位置");
                }}
                type="button"
                className="rounded-full bg-slate-100 px-3 py-1.5 text-xs text-slate-600 transition hover:bg-blue-50 hover:text-blue-700"
              >
                {prompt.length > 28 ? `${prompt.slice(0, 28)}...` : prompt}
              </button>
            ))}
          </div>
        </div>
      </div>
      {pendingLocation && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/30 px-4">
          <div className="w-full max-w-md rounded-lg bg-white p-5 shadow-xl">
            <h3 className="text-base font-semibold text-slate-950">确认当前位置</h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">将把下面的位置作为本次输入的出发地，发送后不会继续固定使用。</p>
            <div className="mt-3 rounded-md bg-slate-50 px-3 py-3">
              <div className="text-sm font-semibold text-slate-950">{formatLocationLabel(pendingLocation)}</div>
              {pendingLocation.formatted_address && (
                <div className="mt-1 text-xs leading-5 text-slate-500">{pendingLocation.formatted_address}</div>
              )}
              {!pendingLocation.formatted_address && (
                <div className="mt-1 text-xs leading-5 text-slate-500">浏览器已给出定位点，但后端未能反查到可读地址。</div>
              )}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button
                onClick={() => setPendingLocation(null)}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
              >
                取消
              </button>
              <button
                onClick={confirmCurrentLocation}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
              >
                确认使用
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
