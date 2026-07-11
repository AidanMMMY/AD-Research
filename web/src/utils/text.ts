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
