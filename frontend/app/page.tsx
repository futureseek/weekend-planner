"use client";

import { useState, useRef, useCallback } from "react";
import Chat from "@/components/Chat";
import Canvas, { Itinerary } from "@/components/Canvas";

export default function Home() {
  const [itinerary, setItinerary] = useState<Itinerary | null>(null);
  const [canvasOpen, setCanvasOpen] = useState(false);
  const addExternalMessageRef = useRef<((userMsg: string, reply: string) => void) | null>(null);

  const handleItinerary = (data: Itinerary | null) => {
    if (data) {
      setItinerary(data);
      setCanvasOpen(true);
    }
  };

  const handleChatReady = useCallback((_sendText: (text: string) => void, addExternalMessage: (userMsg: string, reply: string) => void) => {
    addExternalMessageRef.current = addExternalMessage;
  }, []);

  return (
    <main className="h-screen flex flex-col">
      <header className="bg-white border-b px-6 py-3 flex items-center gap-2 shrink-0">
        <span className="text-xl">🗺️</span>
        <h1 className="text-lg font-semibold">周末去哪儿 · AI行程规划</h1>
        {itinerary && !canvasOpen && (
          <button
            onClick={() => setCanvasOpen(true)}
            className="ml-auto text-sm text-blue-500 hover:text-blue-700 border border-blue-300 rounded-full px-3 py-1"
          >
            📋 查看行程
          </button>
        )}
      </header>

      <div className="flex-1 flex overflow-hidden">
        <div className={`${canvasOpen ? "w-1/2" : "w-full"} transition-all duration-300 border-r`}>
          <Chat onItinerary={handleItinerary} onReady={handleChatReady} />
        </div>
        {canvasOpen && (
          <div className="w-1/2">
            <Canvas
              itinerary={itinerary}
              onClose={() => setCanvasOpen(false)}
              onItineraryUpdate={(updated) => setItinerary(updated)}
              onAdjustResult={(userMsg, reply) => addExternalMessageRef.current?.(userMsg, reply)}
            />
          </div>
        )}
      </div>
    </main>
  );
}
