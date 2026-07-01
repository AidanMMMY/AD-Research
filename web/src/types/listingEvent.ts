/** Listing / IPO event frontend types.
 *
 * Mirrors `app/schemas/listing_event.py`. Kept in sync manually — the
 * backend is the source of truth. */

export type ListingStatus = 'upcoming' | 'subscribing' | 'listed' | 'unknown';

export interface ListingEvent {
  id: number;
  ts_code: string;
  sub_code: string | null;
  name: string;
  market: string | null;
  board: string | null;
  industry: string | null;
  issue_date: string | null; // ISO date
  list_date: string | null; // ISO date
  issue_price: number | null;
  pe_ratio: number | null;
  limit_amount: number | null;
  funds_raised: number | null;
  market_amount: number | null;
  sponsor: string | null;
  underwriter: string | null;
  status: ListingStatus;
  source: string;
  fetched_at: string | null;
  updated_at: string | null;
}

export interface ListingEventDetail extends ListingEvent {
  raw_payload: Record<string, unknown> | null;
  created_at: string | null;
}

export interface ListingEventListResponse {
  items: ListingEvent[];
  total: number;
  page: number;
  page_size: number;
  updated_at: string | null;
}

export interface ListingEventFacets {
  industries: string[];
  boards: string[];
  markets: string[];
  statuses: ListingStatus[];
}

export interface ListingEventListParams {
  page?: number;
  page_size?: number;
  boards?: string[];
  markets?: string[];
  statuses?: ListingStatus[];
  industry?: string;
  start_date?: string; // YYYY-MM-DD
  end_date?: string; // YYYY-MM-DD
  date_field?: 'list_date' | 'issue_date';
  q?: string;
  sort_by?: 'list_date' | 'issue_date' | 'funds_raised' | 'issue_price' | 'pe_ratio' | 'updated_at';
  sort_dir?: 'asc' | 'desc';
}

/** UI-friendly label mapping for the `status` enum. */
export const STATUS_LABEL: Record<ListingStatus, string> = {
  upcoming: '即将上市',
  subscribing: '申购中',
  listed: '已上市',
  unknown: '未知',
};