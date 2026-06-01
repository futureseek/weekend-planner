import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Roam 漫游 · AI路线规划",
  description: "用聊天的方式描述出行需求，Roam 生成多方案路线",
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
