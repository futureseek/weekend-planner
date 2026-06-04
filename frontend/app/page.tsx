"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import Chat from "@/components/Chat";
import Canvas, { Itinerary } from "@/components/Canvas";

type Language = "zh" | "en";

const HEADER_TEXT = {
  zh: {
    title: "Roam 漫游",
    badge: "本地路线规划",
    subtitle: "区域 POI 检索 · 多日拆分 · 升级建议 · 个性化预算",
    features: ["多方案", "预算匹配", "升级建议", "地图联动"],
    showCanvas: "查看路线板",
    switchLabel: "EN",
  },
  en: {
    title: "Roam",
    badge: "Local route planner",
    subtitle: "Area POI search · Multi-day split · Upgrade ideas · Personalized budget",
    features: ["Options", "Budget fit", "Upgrade ideas", "Map linked"],
    showCanvas: "Show route board",
    switchLabel: "中文",
  },
};

export default function Home() {
  const sessionId = useMemo(() => {
    if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
      return `web-${crypto.randomUUID()}`;
    }
    return `web-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }, []);
  const [itinerary, setItinerary] = useState<Itinerary | null>(null);
  const [canvasOpen, setCanvasOpen] = useState(false);
  const [language, setLanguage] = useState<Language>("zh");
  const addExternalMessageRef = useRef<((userMsg: string, reply: string, itinerary?: Itinerary) => void) | null>(null);
  const t = HEADER_TEXT[language];

  const handleItinerary = (data: Itinerary | null) => {
    if (data) {
      setItinerary(data);
      setCanvasOpen(true);
    }
  };

  const handleChatReady = useCallback((
    _sendText: (text: string) => void,
    addExternalMessage: (userMsg: string, reply: string, itinerary?: Itinerary) => void
  ) => {
    addExternalMessageRef.current = addExternalMessage;
  }, []);

  return (
    <main className="flex h-screen flex-col bg-slate-100 text-slate-950">
      <header className="shrink-0 border-b border-slate-200 bg-white/95 px-6 py-3 shadow-sm backdrop-blur">
        <div className="flex items-center gap-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-950 text-sm font-bold text-white shadow-sm">
            R
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-semibold tracking-tight text-slate-950">{t.title}</h1>
              <span className="hidden rounded-full bg-sky-50 px-2 py-0.5 text-[11px] font-medium text-sky-700 sm:inline">
                {t.badge}
              </span>
            </div>
            <p className="mt-0.5 truncate text-xs text-slate-500">
              {t.subtitle}
            </p>
          </div>
          <div
            className="ml-1 flex shrink-0 items-center rounded-full border border-blue-200 bg-blue-50 p-1 shadow-sm"
            aria-label="Language switcher"
          >
            <button
              type="button"
              onClick={() => setLanguage("zh")}
              aria-pressed={language === "zh"}
              className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
                language === "zh"
                  ? "bg-blue-600 text-white shadow-sm"
                  : "text-blue-700 hover:bg-white/80"
              }`}
            >
              中文
            </button>
            <button
              type="button"
              onClick={() => setLanguage("en")}
              aria-pressed={language === "en"}
              className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
                language === "en"
                  ? "bg-blue-600 text-white shadow-sm"
                  : "text-blue-700 hover:bg-white/80"
              }`}
            >
              EN
            </button>
          </div>
          <div className="ml-auto hidden items-center gap-2 text-xs text-slate-600 lg:flex">
            <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1">{t.features[0]}</span>
            <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-emerald-700">{t.features[1]}</span>
            <span className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-amber-700">{t.features[2]}</span>
            <span className="rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-sky-700">{t.features[3]}</span>
          </div>
          {itinerary && !canvasOpen && (
            <button
              onClick={() => setCanvasOpen(true)}
              className="rounded-lg border border-blue-200 px-3 py-1.5 text-sm font-medium text-blue-700 transition hover:bg-blue-50"
            >
              {t.showCanvas}
            </button>
          )}
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <div
          className="min-w-0 border-r border-slate-200 transition-[width] duration-200"
          style={{ width: canvasOpen ? "50%" : "100%" }}
        >
          <Chat sessionId={sessionId} onItinerary={handleItinerary} onReady={handleChatReady} language={language} />
        </div>
        {canvasOpen && (
          <div className="min-w-0" style={{ width: "50%" }}>
            <Canvas
              itinerary={itinerary}
              onClose={() => setCanvasOpen(false)}
              onItineraryUpdate={(updated) => setItinerary(updated)}
              onAdjustResult={(userMsg, reply, updated) => addExternalMessageRef.current?.(userMsg, reply, updated)}
              sessionId={sessionId}
              language={language}
            />
          </div>
        )}
      </div>
    </main>
  );
}
