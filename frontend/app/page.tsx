import Chat from "@/components/Chat";

export default function Home() {
  return (
    <main className="h-screen flex flex-col">
      {/* Header */}
      <header className="bg-white border-b px-6 py-3 flex items-center gap-2">
        <span className="text-xl">🗺️</span>
        <h1 className="text-lg font-semibold">周末去哪儿 · AI行程规划</h1>
      </header>

      {/* Chat Area */}
      <div className="flex-1 overflow-hidden">
        <Chat />
      </div>
    </main>
  );
}
