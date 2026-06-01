"use client";

import { Fragment, ReactNode } from "react";

type MarkdownBlock =
  | { type: "heading"; level: number; text: string }
  | { type: "paragraph"; text: string }
  | { type: "ul"; items: string[] }
  | { type: "ol"; items: string[] };

function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }

    const token = match[0];
    if (token.startsWith("**")) {
      nodes.push(
        <strong key={`${match.index}-strong`} className="font-semibold text-slate-950">
          {token.slice(2, -2)}
        </strong>
      );
    } else if (token.startsWith("`")) {
      nodes.push(
        <code
          key={`${match.index}-code`}
          className="rounded bg-slate-100 px-1 py-0.5 text-[0.92em] text-slate-800"
        >
          {token.slice(1, -1)}
        </code>
      );
    } else {
      const linkMatch = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      const href = linkMatch?.[2] ?? "#";
      nodes.push(
        <a
          key={`${match.index}-link`}
          href={href}
          target="_blank"
          rel="noreferrer"
          className="font-medium text-blue-600 underline decoration-blue-200 underline-offset-2 hover:text-blue-700"
        >
          {linkMatch?.[1] ?? token}
        </a>
      );
    }

    lastIndex = match.index + token.length;
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }

  return nodes.map((node, index) => <Fragment key={index}>{node}</Fragment>);
}

function parseBlocks(content: string): MarkdownBlock[] {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const blocks: MarkdownBlock[] = [];
  let paragraph: string[] = [];

  const flushParagraph = () => {
    const text = paragraph.join(" ").trim();
    if (text) {
      blocks.push({ type: "paragraph", text });
    }
    paragraph = [];
  };

  for (let i = 0; i < lines.length; i += 1) {
    const rawLine = lines[i];
    const line = rawLine.trim();

    if (!line) {
      flushParagraph();
      continue;
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      blocks.push({
        type: "heading",
        level: heading[1].length,
        text: heading[2].trim(),
      });
      continue;
    }

    const unordered = line.match(/^[-*]\s+(.+)$/);
    if (unordered) {
      flushParagraph();
      const items = [unordered[1].trim()];
      while (i + 1 < lines.length) {
        const next = lines[i + 1].trim().match(/^[-*]\s+(.+)$/);
        if (!next) break;
        items.push(next[1].trim());
        i += 1;
      }
      blocks.push({ type: "ul", items });
      continue;
    }

    const ordered = line.match(/^\d+[.)]\s+(.+)$/);
    if (ordered) {
      flushParagraph();
      const items = [ordered[1].trim()];
      while (i + 1 < lines.length) {
        const next = lines[i + 1].trim().match(/^\d+[.)]\s+(.+)$/);
        if (!next) break;
        items.push(next[1].trim());
        i += 1;
      }
      blocks.push({ type: "ol", items });
      continue;
    }

    paragraph.push(line);
  }

  flushParagraph();
  return blocks;
}

export default function MarkdownMessage({ content }: { content: string }) {
  const blocks = parseBlocks(content);

  return (
    <div className="space-y-3 text-[15px] leading-7 text-slate-800">
      {blocks.map((block, index) => {
        if (block.type === "heading") {
          const headingClass =
            block.level === 1
              ? "text-lg font-semibold text-slate-950"
              : "text-base font-semibold text-slate-950";
          return (
            <h3 key={index} className={headingClass}>
              {renderInline(block.text)}
            </h3>
          );
        }

        if (block.type === "ul") {
          return (
            <ul key={index} className="ml-5 list-disc space-y-1">
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex}>{renderInline(item)}</li>
              ))}
            </ul>
          );
        }

        if (block.type === "ol") {
          return (
            <ol key={index} className="ml-5 list-decimal space-y-1">
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex}>{renderInline(item)}</li>
              ))}
            </ol>
          );
        }

        return <p key={index}>{renderInline(block.text)}</p>;
      })}
    </div>
  );
}
