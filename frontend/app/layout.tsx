import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "周末去哪儿 · AI行程规划助手",
  description: "用聊天的方式描述出行需求，AI生成行程方案",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
