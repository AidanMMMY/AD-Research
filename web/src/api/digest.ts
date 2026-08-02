import client from './client';

/**
 * 每日夜间 AI 综合研报（digest）API 客户端。
 *
 * 契约（2026-08-02 与后端 Agent 对齐，后端按此实现）：
 * - GET /digest                  → 分页列表（不含 content_md）
 * - GET /digest/latest           → 最新一篇完整报告（含 content_md + sections_json）
 * - GET /digest/latest/summary   → 轻量摘要（可能 404 = 还没有任何报告）
 * - GET /digest/by-date/{date}   → 指定日完整报告（404 = 该日无报告）
 *
 * 全部走现有 axios 实例（JWT 拦截器自动附加）。
 */

/** 报告生成状态：partial = 有章节降级/缺失。 */
export type DigestStatus = 'pending' | 'running' | 'success' | 'partial' | 'failed';

/** 单章节采集/生成状态。 */
export type DigestSectionStatus = 'ok' | 'degraded' | 'failed';

export interface DigestListItem {
  id: number;
  /** YYYY-MM-DD */
  report_date: string;
  title: string;
  status: DigestStatus;
  summary_md: string | null;
  content_chars: number;
}

export interface DigestListResponse {
  items: DigestListItem[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface DigestSection {
  key: string;
  title: string;
  status: DigestSectionStatus;
  chars: number;
  retries: number;
}

/** 完整报告（/latest 与 /by-date 返回结构）。 */
export interface DigestReport {
  id: number;
  report_date: string;
  title: string;
  status: DigestStatus;
  summary_md: string | null;
  content_md: string | null;
  sections_json: DigestSection[];
  llm_model: string | null;
  finished_at: string | null;
}

/** /latest/summary 轻量结构。 */
export interface DigestLatestSummary {
  id: number;
  report_date: string;
  title: string;
  status: DigestStatus;
  summary_md: string | null;
  content_chars: number;
}

/** 后端 404 语义 = 无报告（非错误页），UI 据此走空态。 */
export function isDigestNotFound(error: unknown): boolean {
  return (error as { response?: { status?: number } } | null)?.response?.status === 404;
}

const BASE = '/digest';

export const digestApi = {
  getList: (params?: { page?: number; page_size?: number }) =>
    client.get<DigestListResponse>(BASE, { params }),
  getLatest: () => client.get<DigestReport>(`${BASE}/latest`),
  getLatestSummary: () => client.get<DigestLatestSummary>(`${BASE}/latest/summary`),
  getByDate: (date: string) => client.get<DigestReport>(`${BASE}/by-date/${date}`),
};

export const DIGEST_STALE_TIME = 5 * 60_000;

/** react-query retry 策略：404 = 空态不重试，其余错误最多重试 2 次。 */
export function digestRetry(failureCount: number, error: unknown): boolean {
  return !isDigestNotFound(error) && failureCount < 2;
}
