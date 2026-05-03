"use client";

import { useState, useRef, useEffect } from "react";

interface ItineraryBlock {
  id: string;
  type: string;
  icon: string;
  name: string;
  duration: number;
  price: number;
  recommendation: string;
  address: string;
}

interface Itinerary {
  blocks: ItineraryBlock[];
  connections: { from: string; to: string; distance: string; time: string }[];
  total_duration: number;
  total_price: number;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  itinerary?: Itinerary | null;
}

const LOADING_TEXTS = [
  "思考中...",
  "理解需求中...",
  "查找地点中...",
  "规划路线中...",
  "生成方案中...",
  "总结中...",
];

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingTextIndex, setLoadingTextIndex] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (!loading) {
      setLoadingTextIndex(0);
      return;
    }
    const timer = setInterval(() => {
      setLoadingTextIndex((prev) => (prev + 1) % LOADING_TEXTS.length);
    }, 2000);
    return () => clearInterval(timer);
  }, [loading]);

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || loading) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setLoading(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: "default" }),
      });

      if (!res.ok) throw new Error("请求失败");

      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.reply,
          itinerary: data.itinerary,
        },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "抱歉，出了点问题，请稍后再试。" },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const renderItinerary = (itinerary: Itinerary) => {
    return (
      <div className="mt-3 space-y-2">
        {itinerary.blocks.map((block) => (
          <div
            key={block.id}
            className="bg-gradient-to-r from-blue-50 to-purple-50 rounded-xl p-3 border border-blue-100"
          >
            <div className="flex items-center gap-2">
              <span className="text-xl">{block.icon}</span>
              <span className="font-medium">{block.name}</span>
              <span className="text-xs text-gray-500 ml-auto">
                {block.duration}min · ¥{block.price}
              </span>
            </div>
            <p className="text-sm text-gray-600 mt-1">{block.recommendation}</p>
            {block.address && (
              <p className="text-xs text-gray-400 mt-1">📍 {block.address}</p>
            )}
          </div>
        ))}
        {itinerary.total_price > 0 && (
          <div className="text-xs text-gray-500 text-right pt-1">
            预计 {itinerary.total_duration}min · ¥{itinerary.total_price}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-400 mt-20">
            <p className="text-2xl mb-2">👋</p>
            <p>告诉我你想去哪玩，我来帮你规划！</p>
            <p className="text-sm mt-1">
              例如：周六下午在杭州，预算300，喜欢探店和看展
            </p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-2 ${
                msg.role === "user"
                  ? "bg-blue-500 text-white"
                  : "bg-white text-gray-800 shadow-sm"
              }`}
            >
              <p className="whitespace-pre-wrap">{msg.content}</p>
              {msg.itinerary && renderItinerary(msg.itinerary)}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-white rounded-2xl px-4 py-2 shadow-sm">
              <span className="animate-pulse">{LOADING_TEXTS[loadingTextIndex]}</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="border-t bg-white p-4">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendMessage()}
            placeholder="描述你的出行需求..."
            className="flex-1 border rounded-full px-4 py-2 outline-none focus:ring-2 focus:ring-blue-300"
            disabled={loading}
          />
          <button
            onClick={sendMessage}
            disabled={loading || !input.trim()}
            className="bg-blue-500 text-white rounded-full px-6 py-2 hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            发送
          </button>
        </div>
      </div>
    </div>
  );
}
