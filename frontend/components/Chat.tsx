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

type Language = "zh" | "en";

const LOADING_TEXTS: Record<Language, string[]> = {
  zh: [
    "解析城市、时间和预算",
    "检索 POI 和评价线索",
    "计算转场距离和路线顺序",
    "拆分多日行程和备选方案",
  ],
  en: [
    "Parsing city, time and budget",
    "Searching POIs and review signals",
    "Calculating transfers and route order",
    "Splitting days and alternative plans",
  ],
};

const CHAT_TEXT = {
  zh: {
    geoReady: "可使用当前位置",
    geoUnsupported: "浏览器不支持定位",
    geoLocating: "正在定位...",
    geoReverse: "正在识别所在城市/区...",
    geoConfirm: "请确认当前位置",
    geoFailed: "定位失败，可直接输入城市/区域",
    backendFallback: "后端接口没有返回可用结果",
    serviceRetry: "。请确认服务已启动后重试。",
    routeReady: "已生成路线，请查看右侧方案。",
    composerTitle: "本地路线条件",
    locateButton: "定位起点",
    enterHint: "偏好框支持 Enter 发送",
    city: "城市",
    cityPlaceholder: "如 广州",
    checkDistricts: "查区",
    startPoint: "起点",
    startPointPlaceholder: "如 当前位置、广州塔、体育西路",
    dates: "出行日期",
    dailyTime: "时间",
    budget: "预算/元",
    people: "人数",
    districts: "考虑区县，可多选",
    preferencePlaceholder: "只填写偏好、爱好、避雷点：如 想吃好一点、少排队、喜欢夜景和展览、不想太累",
    submit: "生成路线",
    cancel: "取消",
    confirmUse: "确认使用",
    confirmTitle: "确认当前位置",
    confirmDesc: "将把下面的位置作为本次输入的起点，发送后不会继续固定使用。",
    noAddress: "浏览器已给出定位点，但后端未能反查到可读地址。",
    reloadLoading: "加载中...",
    reload: "重新加载到右侧方案",
    currentNear: "当前位置附近",
  },
  en: {
    geoReady: "Current location available",
    geoUnsupported: "Browser location is unavailable",
    geoLocating: "Locating...",
    geoReverse: "Resolving city/district...",
    geoConfirm: "Confirm current location",
    geoFailed: "Location failed. Type city/area instead.",
    backendFallback: "Backend did not return a usable result",
    serviceRetry: ". Please make sure the service is running and retry.",
    routeReady: "Route generated. Check the right panel.",
    composerTitle: "Local route conditions",
    locateButton: "Locate start",
    enterHint: "Press Enter in preferences to send",
    city: "City",
    cityPlaceholder: "e.g. Guangzhou",
    checkDistricts: "Load areas",
    startPoint: "Start point",
    startPointPlaceholder: "e.g. current location, Canton Tower, a metro station",
    dates: "Travel dates",
    dailyTime: "Time",
    budget: "Budget/CNY",
    people: "People",
    districts: "Districts to consider, multi-select",
    preferencePlaceholder: "Only write preferences, hobbies and avoids: better food, fewer queues, night views, exhibitions, not too tiring",
    submit: "Generate",
    cancel: "Cancel",
    confirmUse: "Use location",
    confirmTitle: "Confirm Current Location",
    confirmDesc: "This will be used as the start point for this request only.",
    noAddress: "Browser returned coordinates, but the backend could not resolve a readable address.",
    reloadLoading: "Loading...",
    reload: "Load to route panel again",
    currentNear: "near current location",
  },
};

interface LocationInfo {
  location: string;
  formatted_address?: unknown;
  city?: unknown;
  district?: unknown;
  adcode?: string;
}

interface DistrictOption {
  name: string;
  adcode?: string;
  center?: string;
  level?: string;
}

interface GeocodeSuggestion extends LocationInfo {
  name?: string;
  address?: string;
  province?: string;
  country?: string;
  source?: string;
  type?: string;
  level?: string;
}

function todayString() {
  return new Date().toISOString().slice(0, 10);
}

function currentTimeString() {
  const now = new Date();
  return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
}

function firstText(value: unknown): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    return value.map((item) => firstText(item)).find(Boolean) || "";
  }
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    return firstText(record.name || record.value || record.text || record.address);
  }
  return "";
}

function formatAddress(info: LocationInfo) {
  return firstText(info.formatted_address).replace(/^(中国|中华人民共和国)/, "");
}

function formatLocationLabel(info: LocationInfo, language: Language = "zh") {
  const city = firstText(info.city).replace(/市$/, "");
  const district = firstText(info.district).replace(/区$/, "");
  if (city && district && city !== district) return `${city}${district}`;
  if (city || district) return city || district;
  const address = formatAddress(info);
  if (address) return address;
  return CHAT_TEXT[language].currentNear;
}

function formatSuggestionTitle(item: GeocodeSuggestion, language: Language) {
  return firstText(item.name) || formatAddress(item) || formatLocationLabel(item, language);
}

function formatSuggestionSub(item: GeocodeSuggestion) {
  const sourceLabel = item.source === "poi" || item.source === "tip" ? "POI" : firstText(item.level);
  const address = firstText(item.address) || formatAddress(item);
  if (item.source === "poi" || item.source === "tip") {
    return [address, sourceLabel].filter(Boolean).join(" · ");
  }
  return [address, firstText(item.city), firstText(item.district), sourceLabel].filter(Boolean).join(" · ");
}

function isCurrentLocationKeyword(value: string) {
  return /^(当前位置|当前定位|我的位置|current location|my location)$/i.test(value.trim());
}

function formatDateForMessage(value: string, language: Language = "zh") {
  if (!value) return "";
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return value;
  if (language === "en") return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
  return `${month}月${day}日`;
}

interface ChatProps {
  sessionId: string;
  onItinerary: (itinerary: Itinerary | null) => void;
  language: Language;
  onReady?: (
    sendMessage: (text: string) => void,
    addExternalMessage: (userMsg: string, reply: string, itinerary?: Itinerary) => void
  ) => void;
}

export default function Chat({ sessionId, onItinerary, onReady, language }: ChatProps) {
  const text = CHAT_TEXT[language];
  const loadingTexts = LOADING_TEXTS[language];
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingTextIndex, setLoadingTextIndex] = useState(0);
  const [oneShotLocation, setOneShotLocation] = useState<LocationInfo | null>(null);
  const [pendingLocation, setPendingLocation] = useState<LocationInfo | null>(null);
  const [geoStatus, setGeoStatus] = useState(text.geoReady);
  const [cityName, setCityName] = useState("");
  const [startPoint, setStartPoint] = useState("");
  const [startSuggestions, setStartSuggestions] = useState<GeocodeSuggestion[]>([]);
  const [districtOptions, setDistrictOptions] = useState<DistrictOption[]>([]);
  const [selectedDistricts, setSelectedDistricts] = useState<string[]>([]);
  const [startDate, setStartDate] = useState(todayString());
  const [endDate, setEndDate] = useState(todayString());
  const [startTime, setStartTime] = useState(currentTimeString);
  const [endTime, setEndTime] = useState("22:00");
  const [budgetAmount, setBudgetAmount] = useState("300");
  const [peopleAmount, setPeopleAmount] = useState("1");
  const [composerHeight, setComposerHeight] = useState(360);
  const [loadingPlanIndex, setLoadingPlanIndex] = useState<number | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const resizeRef = useRef<{ startY: number; startHeight: number } | null>(null);
  const currentLocationRequestRef = useRef("");

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loadingTextIndex]);

  useEffect(() => {
    if (!loading) {
      setLoadingTextIndex(0);
      return;
    }
    const timer = setInterval(() => {
      setLoadingTextIndex((prev) => (prev + 1) % loadingTexts.length);
    }, 1500);
    return () => clearInterval(timer);
  }, [loading, loadingTexts.length]);

  useEffect(() => {
    if (!("geolocation" in navigator)) setGeoStatus(text.geoUnsupported);
  }, [text.geoUnsupported]);

  useEffect(() => {
    if (!oneShotLocation && !pendingLocation) setGeoStatus(text.geoReady);
  }, [language, oneShotLocation, pendingLocation, text.geoReady]);

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      if (!resizeRef.current) return;
      const delta = resizeRef.current.startY - event.clientY;
      setComposerHeight(Math.min(560, Math.max(290, resizeRef.current.startHeight + delta)));
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

  const sendText = useCallback(async (rawText: string) => {
    const trimmed = rawText.trim();
    if (!trimmed || loading) return;

    setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
    setLoading(true);

    try {
      const locationForThisSend = oneShotLocation;
      const shouldUseOneShotLocation = Boolean(locationForThisSend)
        && !trimmed.includes("当前位置:")
        && !trimmed.includes("当前位置：")
        && !trimmed.includes("Start point:");
      const enrichedText = shouldUseOneShotLocation
        ? language === "en"
          ? `Start point:${locationForThisSend!.location}, ${formatLocationLabel(locationForThisSend!, language)}\n${trimmed}`
          : `当前位置:${locationForThisSend!.location}，${formatLocationLabel(locationForThisSend!, language)}，${trimmed}`
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
        { role: "assistant", content: data.reply || text.routeReady, itinerary: data.itinerary },
      ]);
    } catch (error) {
      const detail = error instanceof Error && error.message ? `（${error.message}）` : "";
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `${text.backendFallback}${detail}${text.serviceRetry}` },
      ]);
    } finally {
      setLoading(false);
      if (oneShotLocation) {
        setOneShotLocation(null);
        setStartPoint("");
        setGeoStatus(text.geoReady);
      }
    }
  }, [language, loading, oneShotLocation, onItinerary, sessionId, text.backendFallback, text.geoReady, text.routeReady, text.serviceRetry]);

  useEffect(() => {
    onReady?.(sendText, addExternalMessage);
  }, [onReady, sendText]);

  const sendMessage = async () => {
    const text = buildStructuredMessage();
    if (!hasStructuredCore || loading) return;
    setInput("");
    await sendText(text);
  };

  const fetchDistricts = useCallback(async (city: string, preferred?: string) => {
    const normalizedCity = city.trim().replace(/市$/, "");
    if (!normalizedCity) return;
    try {
      const data = await apiPost<{ city: string; districts: DistrictOption[] }>("/api/location/districts", { city: normalizedCity });
      setDistrictOptions(data.districts || []);
      if (preferred) {
        const preferredName = preferred.replace(/区$/, "区");
        const matched = (data.districts || []).find((item) => item.name === preferredName || item.name.includes(preferred.replace(/区$/, "")));
        if (matched) setSelectedDistricts([matched.name]);
      }
    } catch {
      setDistrictOptions([]);
    }
  }, []);

  const toggleDistrict = (name: string) => {
    setSelectedDistricts((prev) => (
      prev.includes(name) ? prev.filter((item) => item !== name) : [...prev, name]
    ));
  };

  const buildStructuredMessage = () => {
    const city = cityName.trim();
    const areas = selectedDistricts.length ? selectedDistricts.join("、") : "";
    const dateRange = startDate && endDate
      ? `${formatDateForMessage(startDate, language)}-${formatDateForMessage(endDate, language)}`
      : startDate ? formatDateForMessage(startDate, language) : "";
    const timeRange = startTime && endTime ? `${startTime}-${endTime}` : "";
    const preferences = input.trim();
    const start = oneShotLocation
      ? `${oneShotLocation.location}，${formatLocationLabel(oneShotLocation, language)}`
      : startPoint.trim();
    if (language === "en") {
      const lines = [
        "[Structured local route request]",
        "Language: English",
        city ? `City: ${city}` : "",
        areas ? `Districts: ${areas}` : "",
        start ? `Start point: ${start}` : "",
        dateRange ? `Travel dates: ${dateRange}` : "",
        timeRange ? `Daily time: ${timeRange}` : "",
        budgetAmount ? `Budget: ${budgetAmount} CNY` : "",
        peopleAmount ? `People: ${peopleAmount}` : "",
        preferences ? `Preferences and hobbies: ${preferences}` : "",
        "Generate multiple executable local POI route options within the selected city/districts. Answer in English.",
      ].filter(Boolean);
      return lines.join("\n");
    }
    const lines = [
      "【结构化本地路线需求】",
      "语言：简体中文",
      city ? `城市：${city}` : "",
      areas ? `考虑区县：${areas}` : "",
      start ? `起点：${start}` : "",
      dateRange ? `出行日期：${dateRange}` : "",
      timeRange ? `每日时间：${timeRange}` : "",
      budgetAmount ? `预算：${budgetAmount}元` : "",
      peopleAmount ? `人数：${peopleAmount}人` : "",
      preferences ? `偏好与爱好：${preferences}` : "",
      "请只在上述城市/区县范围内生成本地多 POI 路线，按时间窗、预算、偏好和转场距离给出多方案。",
    ].filter(Boolean);
    return lines.join("\n");
  };

  const hasStructuredCore = Boolean(
    cityName.trim() &&
    selectedDistricts.length > 0 &&
    startDate &&
    endDate &&
    startTime &&
    endTime &&
    budgetAmount &&
    peopleAmount
  );

  const requestCurrentLocation = () => {
    if (!("geolocation" in navigator)) {
      setGeoStatus(text.geoUnsupported);
      return;
    }
    setGeoStatus(text.geoLocating);
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const location = `${pos.coords.longitude.toFixed(6)},${pos.coords.latitude.toFixed(6)}`;
        setGeoStatus(text.geoReverse);
        try {
          const data = await apiPost<Omit<LocationInfo, "location"> & { location?: string }>("/api/location/reverse", { location });
          const resolved = { ...data, location: data.location || location };
          const label = formatLocationLabel(resolved, language);
          setOneShotLocation(resolved);
          setStartPoint(label);
          setPendingLocation(null);
          setGeoStatus(language === "en" ? `Start set: ${label}` : `已设置起点：${label}`);
        } catch {
          const resolved = { location };
          setOneShotLocation(resolved);
          setStartPoint(text.currentNear);
          setPendingLocation(null);
          setGeoStatus(language === "en" ? "Start set from browser coordinates" : "已用浏览器坐标设置起点");
        }
      },
      () => setGeoStatus(text.geoFailed),
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 5 * 60 * 1000 }
    );
  };

  useEffect(() => {
    const keyword = startPoint.trim();
    if (!keyword || keyword.length < 2 || oneShotLocation || isCurrentLocationKeyword(keyword)) {
      setStartSuggestions([]);
      return;
    }
    const timer = window.setTimeout(async () => {
      try {
        const data = await apiPost<{ items: GeocodeSuggestion[] }>("/api/location/geocode", {
          address: keyword,
          city: cityName,
        });
        setStartSuggestions((data.items || []).filter((item) => item.location).slice(0, 5));
      } catch {
        setStartSuggestions([]);
      }
    }, 320);
    return () => window.clearTimeout(timer);
  }, [cityName, oneShotLocation, startPoint]);

  const handleStartPointChange = (value: string) => {
    setStartPoint(value);
    if (oneShotLocation) setOneShotLocation(null);
    if (isCurrentLocationKeyword(value) && currentLocationRequestRef.current !== value.trim()) {
      currentLocationRequestRef.current = value.trim();
      requestCurrentLocation();
    } else if (!isCurrentLocationKeyword(value)) {
      currentLocationRequestRef.current = "";
    }
  };

  const selectStartSuggestion = (item: GeocodeSuggestion) => {
    const label = formatSuggestionTitle(item, language);
    setOneShotLocation(item);
    setStartPoint(label);
    setStartSuggestions([]);
    setGeoStatus(language === "en" ? `Start set: ${label}` : `已设置起点：${label}`);
  };

  const detectedFields = useMemo(() => {
    const chips = [];
    if (cityName.trim()) chips.push(language === "en" ? "City√" : "城市√");
    if (selectedDistricts.length) chips.push(language === "en" ? "District√" : "区县√");
    if (startPoint.trim() || oneShotLocation) chips.push(language === "en" ? "Start√" : "起点√");
    if (startDate && endDate && startTime && endTime) chips.push(language === "en" ? "Time√" : "时间√");
    if (budgetAmount) chips.push(language === "en" ? "Budget√" : "预算√");
    if (peopleAmount) chips.push(language === "en" ? "People√" : "人数√");
    if (input.trim()) chips.push(language === "en" ? "Preference√" : "偏好√");
    return chips;
  }, [budgetAmount, cityName, endDate, endTime, input, language, oneShotLocation, peopleAmount, selectedDistricts.length, startDate, startPoint, startTime]);
  const completionPct = Math.min(100, Math.round((detectedFields.length / 7) * 100));

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
    <div className="flex h-full flex-col bg-slate-100">
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="mx-auto flex min-h-full w-full max-w-7xl flex-col gap-5">
          {messages.length === 0 && (
            <div className="grid flex-1 content-start gap-4 py-3">
              <section className="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
                <div className="rounded-lg border border-slate-200 bg-white p-7 shadow-sm">
                  <div className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-600">Roam Route Studio</div>
                  <h2 className="mt-3 max-w-3xl text-3xl font-semibold tracking-tight text-slate-950">
                    {language === "en" ? "Plan a local route you can actually follow today" : "把想去的本地目的地，排成今天能直接执行的路线"}
                  </h2>
                  <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
                    {language === "en"
                      ? "Choose the city, districts, dates, start point, budget and people below, then describe what you like. Roam will balance POIs, food, events, transfers and pace into several route styles."
                      : "在下方确定城市、区县、日期、起点、预算和人数，再写下偏好。Roam 会把 POI、餐饮、活动、转场和节奏组合成多种风格路线。"}
                  </p>
                  <div className="mt-6 flex flex-wrap gap-2">
                    {(language === "en"
                      ? ["Better food + relax", "Exhibitions + night view", "Gaming + late dinner", "Hiking + easy finish", "Family light day"]
                      : ["吃好一点，再放松一下", "看展加夜景", "打游戏加夜宵", "爬山后轻松收尾", "亲子轻松半日"]
                    ).map((item) => (
                      <button
                        key={item}
                        type="button"
                        onClick={() => setInput(item)}
                        className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700"
                      >
                        {item}
                      </button>
                    ))}
                  </div>
                  <div className="mt-8 grid gap-4 sm:grid-cols-3">
                    {(language === "en"
                      ? [
                          ["Multi-style", "Balanced, food-first, fewer queues and budget-fit plans."],
                          ["Map sketch", "Numbered stops and transfer lines stay aligned with the route."],
                          ["Daily checklist", "Times, costs, stop types and next-leg info are ready to execute."],
                        ]
                      : [
                          ["多风格方案", "综合、吃好玩好、少排队、预算匹配可切换。"],
                          ["路线草图", "数字标点和转场线跟方案顺序保持一致。"],
                          ["执行清单", "时间、花费、地点类型和下一段转场可直接照着走。"],
                        ]
                    ).map(([title, desc]) => (
                      <div key={title} className="border-l border-slate-200 pl-4">
                        <div className="text-sm font-semibold text-slate-950">{title}</div>
                        <div className="mt-2 text-xs leading-5 text-slate-600">{desc}</div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">{language === "en" ? "Route Preview" : "路线预览"}</div>
                      <h3 className="mt-2 text-base font-semibold text-slate-950">{language === "en" ? "Map first, checklist below" : "先看路线，再看执行清单"}</h3>
                    </div>
                    <span className="rounded-full bg-sky-50 px-3 py-1 text-xs font-medium text-sky-700">{language === "en" ? "Linked" : "联动"}</span>
                  </div>
                  <div className="mt-5 overflow-hidden rounded-lg border border-slate-200 bg-[#edf7fa]">
                    <div className="relative h-48">
                      <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(148,163,184,0.20)_1px,transparent_1px),linear-gradient(to_bottom,rgba(148,163,184,0.20)_1px,transparent_1px)] bg-[size:34px_34px]" />
                      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" aria-hidden>
                        <path d="M12 68 C24 52, 30 44, 42 45 S61 56, 70 38 S83 28, 90 40" fill="none" stroke="#0284c7" strokeWidth="2.4" strokeLinecap="round" />
                      </svg>
                      {[
                        ["1", "14%", "68%"],
                        ["2", "32%", "45%"],
                        ["3", "54%", "55%"],
                        ["4", "72%", "38%"],
                        ["5", "90%", "40%"],
                      ].map(([num, left, top]) => (
                        <div
                          key={num}
                          className="absolute flex h-9 w-9 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-2 border-white bg-blue-600 text-xs font-semibold text-white shadow-lg"
                          style={{ left, top }}
                        >
                          {num}
                        </div>
                      ))}
                    </div>
                    <div className="grid gap-px bg-slate-200 text-xs sm:grid-cols-3">
                      {(language === "en"
                        ? [["18:30", "Dinner"], ["20:00", "Relax"], ["21:15", "Night view"]]
                        : [["18:30", "正餐"], ["20:00", "放松"], ["21:15", "夜景"]]
                      ).map(([time, title]) => (
                        <div key={time} className="bg-white px-4 py-3">
                          <div className="font-semibold text-slate-950">{time}</div>
                          <div className="mt-1 text-slate-500">{title}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </section>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[88%] rounded-lg px-4 py-3 shadow-sm ${
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
                        {loadingPlanIndex === i ? text.reloadLoading : text.reload}
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
                {loadingTexts[loadingTextIndex]}
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      <div className="relative border-t border-slate-200 bg-white/95 px-6 py-4 shadow-[0_-10px_28px_rgba(15,23,42,0.06)]">
        <div
          onMouseDown={startComposerResize}
          className="absolute left-0 right-0 top-0 h-3 cursor-ns-resize"
          aria-label="拖拽调整输入面板高度"
        />
        <div
          className="mx-auto flex w-full max-w-7xl flex-col rounded-lg border border-slate-200 bg-white p-4 shadow-sm focus-within:border-blue-400 focus-within:ring-2 focus-within:ring-blue-100"
          style={{ height: composerHeight }}
        >
          <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-3">
                <label htmlFor="travel-requirement" className="text-sm font-semibold text-slate-950">
                  {text.composerTitle}
                </label>
                <div className="hidden h-1.5 w-28 overflow-hidden rounded-full bg-slate-100 sm:block">
                  <div className="h-full rounded-full bg-emerald-400 transition-all" style={{ width: `${completionPct}%` }} />
                </div>
                <span className="hidden text-[11px] font-medium text-slate-400 sm:inline">{completionPct}%</span>
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {detectedFields.length ? detectedFields.map((chip) => (
                  <span key={chip} className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700">
                    {chip}
                  </span>
                )) : <span className="text-xs text-slate-500">{geoStatus}</span>}
              </div>
            </div>
            <span className="text-xs text-slate-400">{text.enterHint}</span>
          </div>

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-[0.9fr_1fr_1.2fr_0.8fr_0.7fr]">
            <label className="text-xs font-medium text-slate-500">
              {text.city}
              <div className="mt-1 flex gap-2">
                <input
                  value={cityName}
                  onChange={(e) => {
                    setCityName(e.target.value);
                    setSelectedDistricts([]);
                    setDistrictOptions([]);
                  }}
                  onBlur={() => fetchDistricts(cityName)}
                  placeholder={text.cityPlaceholder}
                  className="h-9 w-full rounded-lg border border-slate-200 px-3 text-sm text-slate-900 outline-none focus:border-blue-400"
                />
                <button
                  type="button"
                  onClick={() => fetchDistricts(cityName)}
                  className="h-9 shrink-0 rounded-lg border border-slate-200 px-3 text-xs text-slate-600 hover:bg-slate-50"
                >
                  {text.checkDistricts}
                </button>
              </div>
            </label>
            <label className="relative text-xs font-medium text-slate-500">
              {text.startPoint}
              <div className="mt-1 flex gap-2">
                <input
                  value={startPoint}
                  onChange={(e) => handleStartPointChange(e.target.value)}
                  placeholder={text.startPointPlaceholder}
                  className="h-9 w-full rounded-lg border border-slate-200 px-3 text-sm text-slate-900 outline-none focus:border-blue-400"
                />
                <button
                  type="button"
                  onClick={requestCurrentLocation}
                  className="h-9 shrink-0 rounded-lg border border-blue-200 bg-blue-50 px-3 text-xs font-medium text-blue-700 transition hover:border-blue-300 hover:bg-blue-100"
                >
                  {text.locateButton}
                </button>
              </div>
              {startSuggestions.length > 0 && (
                <div className="absolute left-0 right-0 top-[64px] z-30 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-xl">
                  {startSuggestions.map((item) => {
                    const label = formatSuggestionTitle(item, language);
                    const sub = formatSuggestionSub(item);
                    const isPoi = item.source === "poi" || item.source === "tip";
                    return (
                      <button
                        key={`${item.location}-${label}`}
                        type="button"
                        onClick={() => selectStartSuggestion(item)}
                        className="block w-full px-3 py-2 text-left transition hover:bg-blue-50"
                      >
                        <div className="flex min-w-0 items-center gap-2">
                          <span className="truncate text-sm font-medium text-slate-800">{label}</span>
                          {isPoi && <span className="shrink-0 rounded-full bg-blue-50 px-1.5 py-0.5 text-[10px] font-semibold text-blue-700">POI</span>}
                        </div>
                        {sub && <div className="mt-0.5 truncate text-[11px] text-slate-400">{sub}</div>}
                      </button>
                    );
                  })}
                </div>
              )}
            </label>
            <div className="text-xs font-medium text-slate-500">
              {text.dates}
              <div className="mt-1 grid grid-cols-2 gap-2">
                <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="h-9 rounded-lg border border-slate-200 px-3 text-sm text-slate-900 outline-none focus:border-blue-400" />
                <input type="date" value={endDate} min={startDate} onChange={(e) => setEndDate(e.target.value)} className="h-9 rounded-lg border border-slate-200 px-3 text-sm text-slate-900 outline-none focus:border-blue-400" />
              </div>
            </div>
            <div className="text-xs font-medium text-slate-500">
              {text.dailyTime}
              <div className="mt-1 grid grid-cols-2 gap-2">
                <input type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} className="h-9 rounded-lg border border-slate-200 px-3 text-sm text-slate-900 outline-none focus:border-blue-400" />
                <input type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} className="h-9 rounded-lg border border-slate-200 px-3 text-sm text-slate-900 outline-none focus:border-blue-400" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <label className="text-xs font-medium text-slate-500">
                {text.budget}
                <input inputMode="numeric" value={budgetAmount} onChange={(e) => setBudgetAmount(e.target.value.replace(/\D/g, ""))} placeholder="2000" className="mt-1 h-9 w-full rounded-lg border border-slate-200 px-3 text-sm text-slate-900 outline-none focus:border-blue-400" />
              </label>
              <label className="text-xs font-medium text-slate-500">
                {text.people}
                <input inputMode="numeric" value={peopleAmount} onChange={(e) => setPeopleAmount(e.target.value.replace(/\D/g, ""))} placeholder="2" className="mt-1 h-9 w-full rounded-lg border border-slate-200 px-3 text-sm text-slate-900 outline-none focus:border-blue-400" />
              </label>
            </div>
          </div>

          <div className="mt-3 min-h-0 flex-1 overflow-y-auto">
            {districtOptions.length > 0 && (
              <div className="mb-3">
                <div className="mb-1 text-xs font-medium text-slate-500">{text.districts}</div>
                <div className="flex flex-wrap gap-2">
                  {districtOptions.map((district) => {
                    const active = selectedDistricts.includes(district.name);
                    return (
                      <button
                        key={district.name}
                        type="button"
                        onClick={() => toggleDistrict(district.name)}
                        className={`rounded-full border px-3 py-1 text-xs transition ${
                          active ? "border-blue-500 bg-blue-50 text-blue-700" : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                        }`}
                      >
                        {district.name}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
            <div className="flex min-h-[88px] gap-3">
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
                placeholder={text.preferencePlaceholder}
                className="min-h-0 flex-1 resize-none rounded-lg border border-slate-200 bg-white px-3 py-2 text-[15px] leading-7 text-slate-900 outline-none placeholder:text-slate-400 focus:border-blue-400"
                disabled={loading}
              />
              <button
                onClick={sendMessage}
                disabled={loading || !hasStructuredCore}
                className="h-12 self-end rounded-lg bg-blue-600 px-5 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
              >
                {text.submit}
              </button>
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {(language === "en"
                ? ["fewer queues", "better food", "night view", "exhibitions", "shopping", "hiking", "gaming", "family easy"]
                : ["少排队", "吃好一点", "夜景", "看展", "逛街", "爬山", "打游戏", "亲子轻松"]
              ).map((tag) => (
                <button
                  key={tag}
                  type="button"
                  onClick={() => setInput((prev) => prev.includes(tag) ? prev : `${prev}${prev ? "，" : ""}${tag}`)}
                  className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600 transition hover:bg-blue-50 hover:text-blue-700"
                >
                  {tag}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
