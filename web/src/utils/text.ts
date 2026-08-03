/** Text sanitisation helpers used before rendering AI / Jina output. */

const THINK_TAG_RE = /<<\s*think\s*>[\s\S]*?<\s*\/\s*think\s*>/gi;

function normalizeForCompare(text: string): string {
  return text.replace(/\s+/g, '').toLowerCase();
}

/** Remove ``<think>...</think>`` reasoning blocks (DeepSeek-style leakage). */
export function stripThinkTags(text: string): string {
  return text.replace(THINK_TAG_RE, '').trim();
}

/** Remove every standalone line that matches the article title (with or without markdown heading). */
export function removeDuplicateTitle(text: string, title?: string | null): string {
  if (!title || !text) return text;
  const normTitle = normalizeForCompare(title);
  const lines = text.split('\n');
  const out: string[] = [];

  for (const line of lines) {
    const stripped = line.trim();
    if (!stripped) {
      out.push(line);
      continue;
    }
    const heading = normalizeForCompare(stripped.replace(/^#+\s*/, ''));
    if (heading === normTitle) continue;
    out.push(line);
  }

  return out.join('\n').replace(/\n{3,}/g, '\n\n').trim();
}

/**
 * Defence-layer cleanup for the "load full text" body.
 * Strips ``<think>`` tags and removes repeated title lines, regardless of
 * whether the backend has already cleaned the response.
 */
export function cleanNewsFullContent(text: string, title?: string | null): string {
  let cleaned = stripThinkTags(text);
  cleaned = removeDuplicateTitle(cleaned, title);
  return cleaned;
}

/**
 * Render-layer newline guard (2026-08-01 间距修复；2026-08-03 由
 * pages/News/detail.tsx 上提为共享 —— DR1 统一渲染管线).
 * 抓取 / AI 清理 / 译文管线偶尔会在正文里留下 3+ 连续换行（HTML→文本时
 * <p>/<br> 双重换行）。Markdown 渲染器会把多余空行折叠掉，但纯文本
 * pre-wrap 兜底路径不会 —— 每个多余换行都是一整行空白。统一在渲染前
 * 把 3+ 连换行折叠成一个空行；只动渲染输入，不回写数据。
 */
export function collapseBlankRuns(text: string): string {
  return text.replace(/\n{3,}/g, '\n\n');
}

/**
 * 资讯正文的统一渲染前管线（DR1, 2026-08-03）：
 * ``cleanNewsFullContent``（think 块 + 重复标题行）→ ``collapseBlankRuns``
 * （3+ 连换行折叠）。中文译文 / 原文 full_content 都要过同一条管线，
 * detail 页与 NewsDetailDrawer 共用，避免两边清理规则漂移。
 */
export function prepareNewsBody(text: string, title?: string | null): string {
  return collapseBlankRuns(cleanNewsFullContent(text, title));
}
