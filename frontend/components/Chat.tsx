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

const LOCAL_DISTRICTS: Record<string, string[]> = {
  广州: ["越秀区", "海珠区", "荔湾区", "天河区", "白云区", "黄埔区", "番禺区", "花都区", "南沙区", "从化区", "增城区"],
  深圳: ["福田区", "罗湖区", "南山区", "盐田区", "宝安区", "龙岗区", "龙华区", "坪山区", "光明区", "大鹏新区"],
  上海: ["黄浦区", "徐汇区", "长宁区", "静安区", "普陀区", "虹口区", "杨浦区", "闵行区", "宝山区", "嘉定区", "浦东新区", "金山区", "松江区", "青浦区", "奉贤区", "崇明区"],
  北京: ["东城区", "西城区", "朝阳区", "海淀区", "丰台区", "石景山区", "通州区", "昌平区", "大兴区", "顺义区", "房山区", "门头沟区", "怀柔区", "平谷区", "密云区", "延庆区"],
  杭州: ["上城区", "拱墅区", "西湖区", "滨江区", "萧山区", "余杭区", "临平区", "钱塘区", "富阳区", "临安区", "桐庐县", "淳安县", "建德市"],
  成都: ["锦江区", "青羊区", "金牛区", "武侯区", "成华区", "龙泉驿区", "青白江区", "新都区", "温江区", "双流区", "郫都区", "新津区", "都江堰市"],
  重庆: ["渝中区", "江北区", "南岸区", "九龙坡区", "沙坪坝区", "大渡口区", "渝北区", "巴南区", "北碚区", "两江新区"],
  武汉: ["江岸区", "江汉区", "硚口区", "汉阳区", "武昌区", "青山区", "洪山区", "东西湖区", "汉南区", "蔡甸区", "江夏区", "黄陂区", "新洲区"],
  南京: ["玄武区", "秦淮区", "建邺区", "鼓楼区", "浦口区", "栖霞区", "雨花台区", "江宁区", "六合区", "溧水区", "高淳区"],
  苏州: ["姑苏区", "虎丘区", "吴中区", "相城区", "吴江区", "工业园区", "常熟市", "张家港市", "昆山市", "太仓市"],
  西安: ["新城区", "碑林区", "莲湖区", "雁塔区", "未央区", "灞桥区", "长安区", "临潼区", "阎良区", "高陵区", "鄠邑区"],
  天津: ["和平区", "河东区", "河西区", "南开区", "河北区", "红桥区", "滨海新区", "东丽区", "西青区", "津南区", "北辰区", "武清区"],
  厦门: ["思明区", "海沧区", "湖里区", "集美区", "同安区", "翔安区"],
  青岛: ["市南区", "市北区", "李沧区", "崂山区", "城阳区", "黄岛区", "即墨区", "胶州市", "平度市", "莱西市"],
};

const CITY_NAME_ALIASES: Record<string, string> = {
  guangzhou: "广州",
  canton: "广州",
  shenzhen: "深圳",
  shanghai: "上海",
  beijing: "北京",
  hangzhou: "杭州",
  chengdu: "成都",
  chongqing: "重庆",
  wuhan: "武汉",
  nanjing: "南京",
  suzhou: "苏州",
  xian: "西安",
  "xi'an": "西安",
  tianjin: "天津",
  xiamen: "厦门",
  qingdao: "青岛",
};

const PREFERENCE_PRESETS: Record<Language, Array<{ title: string; detail: string; value: string; tone: string }>> = {
  zh: [
    {
      title: "吃顿好的",
      detail: "晚餐提档 · 控排队",
      value: "想吃顿好的，晚餐可以适当多花一点，优先评分高、有特色、排队可控的餐厅",
      tone: "border-amber-200 bg-amber-50 text-amber-900",
    },
    {
      title: "慢咖啡放松",
      detail: "咖啡/甜品 · 少赶路",
      value: "想放松一下，安排慢咖啡、甜品或轻松散步，少赶路，不要太累",
      tone: "border-sky-200 bg-sky-50 text-sky-900",
    },
    {
      title: "夜景收尾",
      detail: "日落后体验更好",
      value: "喜欢夜景和夜游，把适合晚上的景点放到傍晚或晚上，白天不要硬排夜景点",
      tone: "border-indigo-200 bg-indigo-50 text-indigo-900",
    },
    {
      title: "游戏玩乐",
      detail: "电竞/电玩/密室",
      value: "想打游戏或玩点娱乐项目，可以安排电玩城、电竞馆、密室或桌游，晚饭后也可以继续玩",
      tone: "border-violet-200 bg-violet-50 text-violet-900",
    },
    {
      title: "轻徒步",
      detail: "上午户外 · 下午轻松",
      value: "喜欢爬山或户外，但不要暴走，上午安排体力项目，下午留休息和补给",
      tone: "border-emerald-200 bg-emerald-50 text-emerald-900",
    },
    {
      title: "亲子轻松",
      detail: "少折返 · 多休息",
      value: "亲子或和长辈同行，路线要轻松，少折返，多安排休息点和用餐缓冲",
      tone: "border-rose-200 bg-rose-50 text-rose-900",
    },
  ],
  en: [
    {
      title: "Better dinner",
      detail: "Upgrade meal · fewer queues",
      value: "I want a better dinner, willing to spend more on high-rated local food with manageable queues",
      tone: "border-amber-200 bg-amber-50 text-amber-900",
    },
    {
      title: "Slow cafe",
      detail: "Coffee/dessert · easy pace",
      value: "Keep it relaxed with slow cafes, dessert or an easy walk, fewer transfers and not too tiring",
      tone: "border-sky-200 bg-sky-50 text-sky-900",
    },
    {
      title: "Night ending",
      detail: "Sunset and night view",
      value: "I like night views; place night-view spots in the evening instead of the morning",
      tone: "border-indigo-200 bg-indigo-50 text-indigo-900",
    },
    {
      title: "Gaming",
      detail: "Arcade/esports/escape room",
      value: "Add gaming or entertainment stops such as arcades, esports venues, escape rooms or board games",
      tone: "border-violet-200 bg-violet-50 text-violet-900",
    },
    {
      title: "Light hike",
      detail: "Outdoor AM · easy PM",
      value: "I like hiking or outdoors, but keep it moderate; do active stops in the morning and leave recovery time later",
      tone: "border-emerald-200 bg-emerald-50 text-emerald-900",
    },
    {
      title: "Family easy",
      detail: "Less backtracking · more breaks",
      value: "Family or older travelers; keep the route easy with fewer backtracks, more breaks and meal buffers",
      tone: "border-rose-200 bg-rose-50 text-rose-900",
    },
  ],
};

function normalizeCityForLookup(city: string) {
  const value = city.trim().replace(/市$/, "");
  return CITY_NAME_ALIASES[value.toLowerCase()] || value;
}

function localDistrictOptions(city: string): DistrictOption[] {
  const normalized = normalizeCityForLookup(city);
  return (LOCAL_DISTRICTS[normalized] || []).map((name) => ({ name, level: "district" }));
}

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
    myLocation: "我的位置",
    districtLoading: "正在加载区县...",
    districtLoaded: "已加载 {count} 个区县",
    districtFallback: "已使用本地区县候选",
    districtEmpty: "没有查到区县，请检查城市名",
    districtFailed: "区县加载失败，请确认后端和高德 Key",
    startSearching: "正在搜索起点...",
    startNoResult: "没有找到匹配地点，可换成更完整的地点名",
    startManualHint: "请输入起点并从搜索结果中选择",
    cityLocating: "正在识别当前城市...",
    cityLocated: "已识别当前城市：{city}",
    enterHint: "偏好框支持 Enter 发送",
    city: "城市",
    cityPlaceholder: "如 广州",
    checkDistricts: "查区",
    startPoint: "起点",
    startPointPlaceholder: "请输入起点，如体育西路地铁站",
    dates: "出行日期",
    dailyTime: "时间",
    budget: "预算/元",
    people: "人数",
    districts: "建议优先选 1 个区县，最多 2 个更稳",
    preferencePlaceholder: "写具体一点：想吃顿好的、晚上看夜景、少排队、不要太赶、想打游戏或看展",
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
    myLocation: "My location",
    districtLoading: "Loading districts...",
    districtLoaded: "{count} districts loaded",
    districtFallback: "Using local district candidates",
    districtEmpty: "No districts found. Check the city name.",
    districtFailed: "District loading failed. Check backend and AMap key.",
    startSearching: "Searching start point...",
    startNoResult: "No matched places. Try a more specific name.",
    startManualHint: "Type a start point and choose a search result",
    cityLocating: "Detecting current city...",
    cityLocated: "Detected current city: {city}",
    enterHint: "Press Enter in preferences to send",
    city: "City",
    cityPlaceholder: "e.g. Guangzhou",
    checkDistricts: "Load areas",
    startPoint: "Start point",
    startPointPlaceholder: "Type a start point, e.g. a campus or metro station",
    dates: "Travel dates",
    dailyTime: "Time",
    budget: "Budget/CNY",
    people: "People",
    districts: "Pick 1 district for speed; 2 max recommended",
    preferencePlaceholder: "Be specific: better dinner, night views, fewer queues, relaxed pace, gaming or exhibitions",
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
  name?: unknown;
  address?: unknown;
  formatted_address?: unknown;
  city?: unknown;
  district?: unknown;
  adcode?: string;
  original_location?: string;
  anchor_distance_m?: number;
  browser_accuracy_m?: number;
  source?: string;
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
  const name = firstText(info.name);
  if (name) return name;
  const address = formatAddress(info);
  if (address) return address;
  const city = firstText(info.city).replace(/市$/, "");
  const district = firstText(info.district).replace(/区$/, "");
  if (city && district && city !== district) return `${city}${district}`;
  if (city || district) return city || district;
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

const MAX_LOCATION_ACCURACY_M = 30;
const AMAP_JS_KEY = process.env.NEXT_PUBLIC_AMAP_JS_KEY || "";
const AMAP_SECURITY_JS_CODE = process.env.NEXT_PUBLIC_AMAP_SECURITY_JS_CODE || "";

function formatMeters(value: number) {
  if (!Number.isFinite(value) || value <= 0) return "";
  return value >= 1000 ? `${(value / 1000).toFixed(1)}km` : `${Math.round(value)}m`;
}

type BrowserLocationCandidate = {
  location: string;
  accuracy: number;
  name?: string;
  formatted_address?: string;
  city?: string;
  district?: string;
  adcode?: string;
  source: "amap_js" | "browser";
};

function readAmapLngLat(position: unknown) {
  const record = position as Record<string, unknown> | null;
  if (!record) return null;
  const lng = typeof record.getLng === "function" ? record.getLng() : record.lng;
  const lat = typeof record.getLat === "function" ? record.getLat() : record.lat;
  if (typeof lng !== "number" || typeof lat !== "number") return null;
  return { lng, lat };
}

function loadAmapSdk() {
  if (!AMAP_JS_KEY || typeof window === "undefined") return Promise.reject(new Error("missing amap js key"));
  const scopedWindow = window as typeof window & {
    AMap?: any;
    _AMapSecurityConfig?: { securityJsCode?: string };
    __roamAmapLoading?: Promise<any>;
    __roamAmapReady?: () => void;
  };
  if (scopedWindow.AMap?.Geolocation) return Promise.resolve(scopedWindow.AMap);
  if (scopedWindow.__roamAmapLoading) return scopedWindow.__roamAmapLoading;
  if (AMAP_SECURITY_JS_CODE) {
    scopedWindow._AMapSecurityConfig = { securityJsCode: AMAP_SECURITY_JS_CODE };
  }
  scopedWindow.__roamAmapLoading = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    scopedWindow.__roamAmapReady = () => resolve(scopedWindow.AMap);
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(AMAP_JS_KEY)}&plugin=AMap.Geolocation&callback=__roamAmapReady`;
    script.async = true;
    script.onerror = () => reject(new Error("amap js load failed"));
    document.head.appendChild(script);
  });
  return scopedWindow.__roamAmapLoading;
}

async function locateByAmapJs(): Promise<BrowserLocationCandidate> {
  const AMap = await loadAmapSdk();
  return new Promise((resolve, reject) => {
    const geolocation = new AMap.Geolocation({
      enableHighAccuracy: true,
      timeout: 12000,
      zoomToAccuracy: false,
      showButton: false,
      showMarker: false,
      noIpLocate: 3,
      noGeoLocation: 0,
    });
    geolocation.getCurrentPosition((status: string, result: any) => {
      if (status !== "complete") {
        reject(new Error(result?.message || "amap geolocation failed"));
        return;
      }
      const position = readAmapLngLat(result?.position);
      if (!position) {
        reject(new Error("amap position missing"));
        return;
      }
      const address = result?.addressComponent || {};
      resolve({
        location: `${position.lng.toFixed(6)},${position.lat.toFixed(6)}`,
        accuracy: Number.isFinite(result?.accuracy) ? Math.round(result.accuracy) : 0,
        formatted_address: result?.formattedAddress || "",
        city: firstText(address.city).replace(/市$/, ""),
        district: firstText(address.district),
        adcode: address.adcode || "",
        source: "amap_js",
      });
    });
  });
}

function locateByBrowser(): Promise<BrowserLocationCandidate> {
  if (!("geolocation" in navigator)) return Promise.reject(new Error("browser geolocation unsupported"));
  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({
        location: `${pos.coords.longitude.toFixed(6)},${pos.coords.latitude.toFixed(6)}`,
        accuracy: Number.isFinite(pos.coords.accuracy) ? Math.round(pos.coords.accuracy) : 0,
        source: "browser",
      }),
      () => reject(new Error("browser geolocation failed")),
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 }
    );
  });
}

function locationAccuracy(candidate: BrowserLocationCandidate) {
  return candidate.accuracy && Number.isFinite(candidate.accuracy)
    ? candidate.accuracy
    : Number.POSITIVE_INFINITY;
}

async function locateBestCandidate(): Promise<BrowserLocationCandidate> {
  const candidates: BrowserLocationCandidate[] = [];

  if (AMAP_JS_KEY) {
    try {
      const amapCandidate = await locateByAmapJs();
      candidates.push(amapCandidate);
      if (locationAccuracy(amapCandidate) <= MAX_LOCATION_ACCURACY_M) return amapCandidate;
    } catch {
      // Continue with browser geolocation below; AMap may fail or only expose coarse IP-level data.
    }
  }

  if ("geolocation" in navigator) {
    try {
      const browserCandidate = await locateByBrowser();
      candidates.push(browserCandidate);
      if (locationAccuracy(browserCandidate) <= MAX_LOCATION_ACCURACY_M) return browserCandidate;
    } catch {
      // Fall through and report the best coarse candidate if we have one.
    }
  }

  if (candidates.length) {
    candidates.sort((a, b) => locationAccuracy(a) - locationAccuracy(b));
    return candidates[0];
  }

  return Promise.reject(new Error("geolocation unsupported"));
}

function withTimeout<T>(promise: Promise<T>, timeoutMs: number, message: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error(message)), timeoutMs);
    promise.then(
      (value) => {
        window.clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        window.clearTimeout(timer);
        reject(error);
      }
    );
  });
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
  const [cityName, setCityName] = useState("");
  const [startPoint, setStartPoint] = useState("");
  const [selectedStartSuggestion, setSelectedStartSuggestion] = useState<GeocodeSuggestion | null>(null);
  const [startSuggestions, setStartSuggestions] = useState<GeocodeSuggestion[]>([]);
  const [startSearchStatus, setStartSearchStatus] = useState("");
  const [districtOptions, setDistrictOptions] = useState<DistrictOption[]>([]);
  const [selectedDistricts, setSelectedDistricts] = useState<string[]>([]);
  const [districtStatus, setDistrictStatus] = useState("");
  const [startDate, setStartDate] = useState(todayString());
  const [endDate, setEndDate] = useState(todayString());
  const [startTime, setStartTime] = useState(currentTimeString);
  const [endTime, setEndTime] = useState("22:00");
  const [budgetAmount, setBudgetAmount] = useState("300");
  const [peopleAmount, setPeopleAmount] = useState("1");
  const [composerHeight, setComposerHeight] = useState(405);
  const [loadingPlanIndex, setLoadingPlanIndex] = useState<number | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const resizeRef = useRef<{ startY: number; startHeight: number } | null>(null);
  const autoLocationStartedRef = useRef(false);
  const startSearchSeqRef = useRef(0);
  const startSearchCacheRef = useRef<Map<string, GeocodeSuggestion[]>>(new Map());

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
    const handleMouseMove = (event: MouseEvent) => {
      if (!resizeRef.current) return;
      const delta = resizeRef.current.startY - event.clientY;
      setComposerHeight(Math.min(620, Math.max(405, resizeRef.current.startHeight + delta)));
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

  const sendText = useCallback(async (rawText: string, displayText?: string) => {
    const trimmed = rawText.trim();
    if (!trimmed || loading) return;
    const visibleText = (displayText || trimmed).trim();

    setMessages((prev) => [...prev, { role: "user", content: visibleText }]);
    setLoading(true);

    try {
      const data = await apiPost<{ reply: string; itinerary?: Itinerary; alternatives?: Itinerary[] }>(
        "/api/chat",
        { message: trimmed, session_id: sessionId },
        { timeoutMs: 120000 }
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
    }
  }, [loading, onItinerary, sessionId, text.backendFallback, text.routeReady, text.serviceRetry]);

  useEffect(() => {
    onReady?.(sendText, addExternalMessage);
  }, [onReady, sendText]);

  const sendMessage = async () => {
    const text = buildStructuredMessage(true);
    const displayText = buildStructuredMessage(false);
    if (!hasStructuredCore || loading) return;
    setInput("");
    await sendText(text, displayText);
  };

  const fetchDistricts = useCallback(async (city: string, preferred?: string) => {
    const normalizedCity = normalizeCityForLookup(city);
    if (!normalizedCity) return;
    setDistrictStatus(text.districtLoading);
    try {
      const data = await apiPost<{ city: string; districts: DistrictOption[]; source?: string }>(
        "/api/location/districts",
        { city: normalizedCity },
        { timeoutMs: 6500 }
      );
      const districts = data.districts?.length ? data.districts : localDistrictOptions(normalizedCity);
      setDistrictOptions(districts);
      setDistrictStatus(
        districts.length
          ? data.source === "fallback"
            ? text.districtFallback
            : text.districtLoaded.replace("{count}", String(districts.length))
          : text.districtEmpty
      );
      if (preferred) {
        const preferredName = preferred.replace(/区$/, "区");
        const matched = districts.find((item) => item.name === preferredName || item.name.includes(preferred.replace(/区$/, "")));
        if (matched) setSelectedDistricts([matched.name]);
      }
    } catch {
      const districts = localDistrictOptions(normalizedCity);
      setDistrictOptions(districts);
      setDistrictStatus(districts.length ? text.districtFallback : text.districtFailed);
    }
  }, [text.districtEmpty, text.districtFailed, text.districtFallback, text.districtLoaded, text.districtLoading]);

  const toggleDistrict = (name: string) => {
    setSelectedDistricts((prev) => (
      prev.includes(name) ? prev.filter((item) => item !== name) : [...prev, name]
    ));
  };

  const buildStructuredMessage = (forBackend = false) => {
    const city = cityName.trim();
    const areas = selectedDistricts.length ? selectedDistricts.join("、") : "";
    const dateRange = startDate && endDate
      ? `${formatDateForMessage(startDate, language)}-${formatDateForMessage(endDate, language)}`
      : startDate ? formatDateForMessage(startDate, language) : "";
    const timeRange = startTime && endTime ? `${startTime}-${endTime}` : "";
    const preferences = input.trim();
    const start = startPoint.trim();
    const backendStart = forBackend && selectedStartSuggestion?.location
      ? `${selectedStartSuggestion.location}，${start}`
      : start;
    if (language === "en") {
      const lines = [
        city ? `City: ${city}` : "",
        areas ? `Districts: ${areas}` : "",
        start ? `Start point: ${backendStart}` : "",
        dateRange ? `Travel dates: ${dateRange}` : "",
        timeRange ? `Time: ${timeRange}` : "",
        budgetAmount ? `Budget: ${budgetAmount} CNY` : "",
        peopleAmount ? `People: ${peopleAmount}` : "",
        preferences ? `Preferences and hobbies: ${preferences}` : "",
        forBackend ? "Please generate the best travel plan for these conditions. Answer in English." : "",
      ].filter(Boolean);
      return lines.join("\n");
    }
    const lines = [
      city ? `城市：${city}` : "",
      areas ? `考虑区县：${areas}` : "",
      start ? `起点：${backendStart}` : "",
      dateRange ? `出行日期：${dateRange}` : "",
      timeRange ? `时间：${timeRange}` : "",
      budgetAmount ? `预算：${budgetAmount}元` : "",
      peopleAmount ? `人数：${peopleAmount}人` : "",
      preferences ? `偏好与爱好：${preferences}` : "",
      forBackend ? "请生成最适合该条件的出行方案。" : "",
    ].filter(Boolean);
    return lines.join("\n");
  };

  const hasStructuredCore = Boolean(
    cityName.trim() &&
    selectedDistricts.length > 0 &&
    Boolean(startPoint.trim()) &&
    startDate &&
    endDate &&
    startTime &&
    endTime &&
    budgetAmount &&
    peopleAmount
  );

  const requestCurrentCity = () => {
    if (!AMAP_JS_KEY && !("geolocation" in navigator)) {
      return;
    }
    setDistrictStatus(text.cityLocating);
    const locate = withTimeout(locateBestCandidate(), 9000, "city detection timed out");

    locate
      .then(async (candidate) => {
        const { location } = candidate;
        try {
          const data = await apiPost<Omit<LocationInfo, "location"> & { location?: string }>(
            "/api/location/reverse",
            {
              location,
              accuracy_m: candidate.accuracy,
              city_only: true,
              provider: candidate.source,
              fallback_address: candidate.formatted_address,
              fallback_city: candidate.city,
              fallback_district: candidate.district,
              fallback_adcode: candidate.adcode,
            },
            { timeoutMs: 7000 }
          );
          const resolvedCity = firstText(data.city || candidate.city).replace(/市$/, "");
          const resolvedDistrict = firstText(data.district || candidate.district);
          if (!cityName.trim() && resolvedCity) {
            setCityName(resolvedCity);
            fetchDistricts(resolvedCity, resolvedDistrict);
            setDistrictStatus(text.cityLocated.replace("{city}", resolvedCity));
          }
        } catch {
          const resolvedCity = firstText(candidate.city).replace(/市$/, "");
          const resolvedDistrict = firstText(candidate.district);
          if (!cityName.trim() && resolvedCity) {
            setCityName(resolvedCity);
            fetchDistricts(resolvedCity, resolvedDistrict);
            setDistrictStatus(text.cityLocated.replace("{city}", resolvedCity));
          } else {
            setDistrictStatus("");
          }
        }
      })
      .catch(() => setDistrictStatus(""));
  };

  useEffect(() => {
    if (autoLocationStartedRef.current || !("geolocation" in navigator)) return;
    autoLocationStartedRef.current = true;
    requestCurrentCity();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const keyword = startPoint.trim();
    if (!keyword || keyword.length < 2) {
      setStartSuggestions([]);
      setStartSearchStatus("");
      return;
    }
    if (selectedStartSuggestion && keyword === formatSuggestionTitle(selectedStartSuggestion, language)) {
      setStartSuggestions([]);
      return;
    }
    const cacheKey = `${normalizeCityForLookup(cityName)}|${keyword}`.toLowerCase();
    const cached = startSearchCacheRef.current.get(cacheKey);
    if (cached) {
      setStartSuggestions(cached);
      setStartSearchStatus(cached.length ? "" : text.startNoResult);
      return;
    }
    const seq = ++startSearchSeqRef.current;
    setStartSearchStatus(text.startSearching);
    const timer = window.setTimeout(async () => {
      try {
        const data = await apiPost<{ items: GeocodeSuggestion[] }>("/api/location/geocode", {
          address: keyword,
          city: normalizeCityForLookup(cityName),
        }, { timeoutMs: 8000 });
        if (seq !== startSearchSeqRef.current) return;
        const items = (data.items || []).filter((item) => item.location).slice(0, 6);
        startSearchCacheRef.current.set(cacheKey, items);
        setStartSuggestions(items);
        setStartSearchStatus(items.length ? "" : text.startNoResult);
      } catch {
        if (seq !== startSearchSeqRef.current) return;
        setStartSuggestions([]);
        setStartSearchStatus(text.startNoResult);
      }
    }, 220);
    return () => window.clearTimeout(timer);
  }, [cityName, language, selectedStartSuggestion, startPoint, text.startNoResult, text.startSearching]);

  const handleStartPointChange = (value: string) => {
    setStartPoint(value);
    setSelectedStartSuggestion(null);
    setStartSearchStatus("");
  };

  const selectStartSuggestion = (item: GeocodeSuggestion) => {
    const label = formatSuggestionTitle(item, language);
    setStartPoint(label);
    setSelectedStartSuggestion(item);
    setStartSuggestions([]);
    setStartSearchStatus(language === "en" ? `Start set: ${label}` : `已设置起点：${label}`);
  };

  const applyPreferencePreset = (value: string) => {
    setInput((prev) => {
      if (prev.includes(value)) return prev;
      const joiner = language === "en" ? "; " : "，";
      return prev ? `${prev}${joiner}${value}` : value;
    });
  };

  const detectedFields = useMemo(() => {
    const chips = [];
    if (cityName.trim()) chips.push(language === "en" ? "City√" : "城市√");
    if (selectedDistricts.length) chips.push(language === "en" ? "District√" : "区县√");
    if (startPoint.trim()) chips.push(language === "en" ? "Start√" : "起点√");
    if (startDate && endDate && startTime && endTime) chips.push(language === "en" ? "Time√" : "时间√");
    if (budgetAmount) chips.push(language === "en" ? "Budget√" : "预算√");
    if (peopleAmount) chips.push(language === "en" ? "People√" : "人数√");
    if (input.trim()) chips.push(language === "en" ? "Preference√" : "偏好√");
    return chips;
  }, [budgetAmount, cityName, endDate, endTime, input, language, peopleAmount, selectedDistricts.length, startDate, startPoint, startTime]);
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
                      ? "Choose the city, districts, dates, start point, budget and people below, then describe what you like. Roam will balance POIs, food, upgrade ideas, transfers and pace into several route styles."
                      : "在下方确定城市、区县、日期、起点、预算和人数，再写下偏好。Roam 会把 POI、餐饮、升级建议、转场和节奏组合成多种风格路线。"}
                  </p>
                  <div className="mt-6 flex flex-wrap gap-2">
                    {PREFERENCE_PRESETS[language].slice(0, 5).map((preset) => (
                      <button
                        key={preset.title}
                        type="button"
                        onClick={() => applyPreferencePreset(preset.value)}
                        className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700"
                      >
                        {preset.title}
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
          aria-label={language === "en" ? "Drag to resize input panel" : "拖拽调整输入面板高度"}
        />
        <div
          className="mx-auto flex w-full max-w-7xl flex-col rounded-lg border border-slate-200 bg-white p-4 shadow-sm focus-within:border-blue-400 focus-within:ring-2 focus-within:ring-blue-100"
          style={{ minHeight: composerHeight }}
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
                )) : <span className="text-xs text-slate-500">{text.startManualHint}</span>}
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
                    setDistrictStatus("");
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
              {districtStatus && <div className="mt-1 truncate text-[11px] text-slate-400">{districtStatus}</div>}
            </label>
            <label className="relative text-xs font-medium text-slate-500">
              {text.startPoint}
              <div className="mt-1">
                <input
                  value={startPoint}
                  onChange={(e) => handleStartPointChange(e.target.value)}
                  placeholder={text.startPointPlaceholder}
                  className="h-9 w-full rounded-lg border border-slate-200 px-3 text-sm text-slate-900 outline-none focus:border-blue-400"
                />
              </div>
              <div className="mt-1 truncate text-[11px] text-slate-400">{startSearchStatus || text.startManualHint}</div>
              {startSuggestions.length > 0 && (
                <div className="absolute left-0 top-[82px] z-30 max-h-72 w-[520px] max-w-[calc(100vw-2rem)] overflow-y-auto overflow-x-hidden rounded-lg border border-slate-200 bg-white shadow-xl">
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

          <div className="mt-3">
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
            <div className="mt-3 grid gap-2 md:grid-cols-3 xl:grid-cols-6">
              {PREFERENCE_PRESETS[language].map((preset) => (
                <button
                  key={preset.title}
                  type="button"
                  onClick={() => applyPreferencePreset(preset.value)}
                  className={`rounded-lg border px-3 py-2 text-left transition hover:-translate-y-0.5 hover:shadow-sm ${preset.tone}`}
                >
                  <span className="block text-xs font-semibold">{preset.title}</span>
                  <span className="mt-0.5 block truncate text-[11px] opacity-75">{preset.detail}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
