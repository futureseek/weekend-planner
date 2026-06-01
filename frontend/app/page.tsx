"use client";

import { useMemo, useState, useRef, useCallback } from "react";
import Chat from "@/components/Chat";
import Canvas, { Itinerary } from "@/components/Canvas";

export default function Home() {
  const sessionId = useMemo(() => {
    if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
      return `web-${crypto.randomUUID()}`;
    }
    return `web-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }, []);
  const [itinerary, setItinerary] = useState<Itinerary | null>(null);
  const [canvasOpen, setCanvasOpen] = useState(false);
  const addExternalMessageRef = useRef<((userMsg: string, reply: string, itinerary?: Itinerary) => void) | null>(null);

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
    <main className="flex h-screen flex-col bg-[#f5f7fb]">
      <header className="shrink-0 border-b border-slate-200 bg-white px-6 py-3">
        <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600 text-sm font-bold text-white">
          AI
        </div>
        <div>
          <h1 className="text-lg font-semibold text-slate-950">Roam 漫游</h1>
          <p className="text-xs text-slate-500">全国 POI 检索 · 多日路线 · 活动信号 · 个性化预算</p>
        </div>
        <div className="ml-auto hidden items-center gap-2 text-xs text-slate-500 lg:flex">
          <span className="rounded-full bg-slate-100 px-3 py-1">多方案</span>
          <span className="rounded-full bg-slate-100 px-3 py-1">按天拆分</span>
          <span className="rounded-full bg-slate-100 px-3 py-1">可继续调整</span>
        </div>
        {itinerary && !canvasOpen && (
          <button
            onClick={() => setCanvasOpen(true)}
            className="ml-auto rounded-lg border border-blue-200 px-3 py-1.5 text-sm font-medium text-blue-700 hover:bg-blue-50 lg:ml-0"
          >
            查看行程
          </button>
        )}
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <div className={`${canvasOpen ? "w-[46%]" : "w-full"} min-w-0 border-r border-slate-200 transition-all duration-300`}>
          <Chat sessionId={sessionId} onItinerary={handleItinerary} onReady={handleChatReady} />
        </div>
        {canvasOpen && (
          <div className="min-w-0 flex-1">
            <Canvas
              itinerary={itinerary}
              onClose={() => setCanvasOpen(false)}
              onItineraryUpdate={(updated) => setItinerary(updated)}
              onAdjustResult={(userMsg, reply, updated) => addExternalMessageRef.current?.(userMsg, reply, updated)}
              sessionId={sessionId}
            />
          </div>
        )}
      </div>
    </main>
  );
}
