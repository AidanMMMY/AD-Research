import { useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { prepareNewsBody } from '@/utils/text';

/**
 * Lightweight Markdown renderer used wherever we render text returned
 * by AI / Jina Reader / news captions. Keeps a consistent look across
 * pages and gives us one place to tweak typography later.
 */
export default function Markdown({ source }: { source: string }) {
  return (
    <div className="ad-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {source}
      </ReactMarkdown>
    </div>
  );
}

/**
 * 资讯正文的统一渲染管线（DR1, 2026-08-03）——detail 页与
 * NewsDetailDrawer 共用，避免"详情页清理、抽屉不清理"的双轨漂移。
 *
 * 一条管线 = ``prepareNewsBody``（think 块 / 重复标题行 / 3+ 连换行
 * 清理，见 utils/text.ts）+ ``prose-reading`` editorial 阅读容器 +
 * Markdown 渲染。中文译文与原文 full_content 都走这里。
 */
export function NewsMarkdown({
  source,
  title,
  className,
}: {
  source: string;
  /** 用于剔除正文中重复的标题行；传当前展示的标题（中文优先）。 */
  title?: string | null;
  className?: string;
}) {
  const cleaned = useMemo(
    () => prepareNewsBody(source, title),
    [source, title],
  );
  return (
    <div className={`prose-reading${className ? ` ${className}` : ''}`}>
      <Markdown source={cleaned} />
    </div>
  );
}
