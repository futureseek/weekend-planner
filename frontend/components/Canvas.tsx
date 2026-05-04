"use client";

import { useState, useRef, useEffect, useCallback } from "react";

export interface ItineraryBlock {
  id: string;
  type: string;
  icon: string;
  name: string;
  duration: number;
  price: number;
  recommendation: string;
  address: string;
}

export interface Connection {
  from: string;
  to: string;
  distance: string;
  time: string;
}

export interface Itinerary {
  blocks: ItineraryBlock[];
  connections: Connection[];
  total_duration: number;
  total_price: number;
}

const TYPE_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  cafe:          { bg: "bg-amber-50",   border: "border-amber-200",   text: "text-amber-700" },
  restaurant:    { bg: "bg-orange-50",  border: "border-orange-200",  text: "text-orange-700" },
  food:          { bg: "bg-orange-50",  border: "border-orange-200",  text: "text-orange-700" },
  art:           { bg: "bg-blue-50",    border: "border-blue-200",    text: "text-blue-700" },
  museum:        { bg: "bg-blue-50",    border: "border-blue-200",    text: "text-blue-700" },
  exhibition:    { bg: "bg-blue-50",    border: "border-blue-200",    text: "text-blue-700" },
  park:          { bg: "bg-green-50",   border: "border-green-200",   text: "text-green-700" },
  nature:        { bg: "bg-green-50",   border: "border-green-200",   text: "text-green-700" },
  walk:          { bg: "bg-green-50",   border: "border-green-200",   text: "text-green-700" },
  shop:          { bg: "bg-pink-50",    border: "border-pink-200",    text: "text-pink-700" },
  shopping:      { bg: "bg-pink-50",    border: "border-pink-200",    text: "text-pink-700" },
  entertainment: { bg: "bg-purple-50",  border: "border-purple-200",  text: "text-purple-700" },
  movie:         { bg: "bg-purple-50",  border: "border-purple-200",  text: "text-purple-700" },
};

const DEFAULT_COLOR = { bg: "bg-gray-50", border: "border-gray-200", text: "text-gray-700" };

function getTypeColor(type: string) {
  return TYPE_COLORS[type.toLowerCase()] || DEFAULT_COLOR;
}

interface CanvasProps {
  itinerary: Itinerary | null;
  onClose: () => void;
}

export default function Canvas({ itinerary, onClose }: CanvasProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [blocks, setBlocks] = useState<ItineraryBlock[]>([]);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [lineCoords, setLineCoords] = useState<
    { fromId: string; toId: string; distance: string; x: number; y1: number; y2: number }[]
  >([]);
  const containerRef = useRef<HTMLDivElement>(null);
  const prevItineraryRef = useRef<Itinerary | null>(null);

  useEffect(() => {
    if (itinerary && itinerary !== prevItineraryRef.current) {
      setBlocks(itinerary.blocks);
      setConnections(itinerary.connections);
      prevItineraryRef.current = itinerary;
    }
  }, [itinerary]);

  // Calculate line positions from DOM
  const updateLines = useCallback(() => {
    if (!containerRef.current) return;
    const container = containerRef.current;
    const containerRect = container.getBoundingClientRect();
    const cardEls = container.querySelectorAll("[data-card-id]") as NodeListOf<HTMLElement>;

    const positions: Record<string, { top: number; bottom: number; centerX: number }> = {};
    cardEls.forEach((el) => {
      const id = el.dataset.cardId!;
      const rect = el.getBoundingClientRect();
      positions[id] = {
        top: rect.top - containerRect.top,
        bottom: rect.bottom - containerRect.top,
        centerX: rect.left + rect.width / 2 - containerRect.left,
      };
    });

    const newCoords = connections
      .map((conn) => {
        const from = positions[conn.from];
        const to = positions[conn.to];
        if (!from || !to) return null;
        return {
          fromId: conn.from,
          toId: conn.to,
          distance: conn.distance,
          x: from.centerX,
          y1: from.bottom,
          y2: to.top,
        };
      })
      .filter(Boolean) as typeof lineCoords;

    setLineCoords(newCoords);
  }, [connections]);

  useEffect(() => {
    const timer = setTimeout(updateLines, 100);
    window.addEventListener("resize", updateLines);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("resize", updateLines);
    };
  }, [blocks, updateLines]);

  if (!itinerary) return null;

  const selectedBlock = blocks.find((b) => b.id === selectedId);

  return (
    <div className="h-full flex flex-col bg-gray-50">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b bg-white shrink-0">
        <span className="text-sm font-medium text-gray-600">行程路线</span>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-lg">×</button>
      </div>

      {/* Canvas */}
      <div className="flex-1 overflow-auto">
        <div ref={containerRef} className="relative px-12 py-8 flex flex-col items-center gap-24">
          {/* SVG lines */}
          <svg
            className="absolute top-0 left-0 w-full h-full pointer-events-none"
            style={{ zIndex: 0 }}
          >
            {lineCoords.map((line) => {
              const bendX = line.x + 90;
              const midY = (line.y1 + line.y2) / 2;
              const path = `M ${line.x} ${line.y1} Q ${bendX} ${midY}, ${line.x} ${line.y2}`;

              return (
                <g key={`${line.fromId}-${line.toId}`}>
                  <path
                    d={path}
                    fill="none"
                    stroke="#94a3b8"
                    strokeWidth={1.5}
                    strokeDasharray="8,5"
                    strokeLinecap="round"
                  />
                  <circle cx={line.x} cy={line.y1} r={4} fill="#94a3b8" />
                  <circle cx={line.x} cy={line.y2} r={4} fill="#94a3b8" />
                  <g transform={`translate(${bendX - 10}, ${midY})`}>
                    <rect x={-24} y={-10} width={48} height={20} rx={10} fill="white" stroke="#e2e8f0" />
                    <text x={0} y={4} fontSize={11} fill="#64748b" textAnchor="middle">
                      {line.distance}
                    </text>
                  </g>
                </g>
              );
            })}
          </svg>

          {/* Cards */}
          {blocks.map((block) => {
            const colors = getTypeColor(block.type);
            const isSelected = selectedId === block.id;

            return (
              <div
                key={block.id}
                data-card-id={block.id}
                onClick={() => setSelectedId(isSelected ? null : block.id)}
                className={`
                  w-52 rounded-xl border-2 p-3 bg-white cursor-pointer select-none relative
                  ${isSelected ? "border-blue-400 shadow-md" : `${colors.border} shadow-sm hover:shadow-md`}
                `}
                style={{ zIndex: 1 }}
              >
                <div className="flex items-center gap-2">
                  <span className="text-xl">{block.icon}</span>
                  <span className="font-medium text-sm truncate">{block.name}</span>
                </div>
                <div className="text-xs text-gray-400 mt-1">
                  {block.duration}min · ¥{block.price}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Detail panel */}
      {selectedBlock && (
        <div className="border-t bg-white p-4 shrink-0">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-2xl">{selectedBlock.icon}</span>
            <div>
              <h3 className="font-medium">{selectedBlock.name}</h3>
              <span className={`text-xs px-2 py-0.5 rounded-full ${getTypeColor(selectedBlock.type).bg} ${getTypeColor(selectedBlock.type).text}`}>
                {selectedBlock.type}
              </span>
            </div>
          </div>
          <p className="text-sm text-gray-600 mb-1">{selectedBlock.recommendation}</p>
          <div className="flex gap-4 text-xs text-gray-500">
            <span>⏱ {selectedBlock.duration}分钟</span>
            <span>💰 ¥{selectedBlock.price}</span>
            {selectedBlock.address && <span>📍 {selectedBlock.address}</span>}
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="border-t bg-white px-4 py-2 flex justify-between text-xs text-gray-500 shrink-0">
        <span>共 {blocks.length} 个地点</span>
        <span>预计 {itinerary.total_duration}min · ¥{itinerary.total_price}</span>
      </div>
    </div>
  );
}
