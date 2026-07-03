/** Cninfo periodic-report frontend types.
 *
 * Mirrors `app/schemas/cninfo_report.py`. Backend is source of truth.
 */

export type CninfoAdjunctType = 'annual' | 'semi' | 'q1' | 'q3' | 'other';

export interface CninfoReport {
  id: number;
  ts_code: string;
  stock_name: string | null;
  stock_code: string;
  org_id: string | null;
  sec_code: string | null;
  announcement_id: string;
  announcement_title: string;
  adjunct_url: string;
  file_path: string | null;
  file_size: number | null;
  announcement_time: string; // ISO datetime
  adjunct_type: CninfoAdjunctType | string;
  is_periodic: boolean;
  fiscal_year: number | null;
  fiscal_quarter: number | null;
  extraction_status: string;
  extracted_at: string | null;
  source: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface CninfoReportDetail extends CninfoReport {
  raw_payload: Record<string, unknown> | null;
  extracted_text_preview: string | null;
}

export interface CninfoReportListResponse {
  items: CninfoReport[];
  total: number;
  page: number;
  page_size: number;
  updated_at: string | null;
}

export interface CninfoReportListParams {
  ts_code?: string;
  fiscal_year?: number;
  fiscal_quarter?: number;
  adjunct_type?: CninfoAdjunctType;
  start_date?: string;
  end_date?: string;
  has_text?: boolean;
  page?: number;
  page_size?: number;
}

export interface CninfoReportCoverage {
  total_reports: number;
  stocks_covered: number;
  stocks_with_text: number;
  fiscal_year_breakdown: Record<string, number>;
  adjunct_type_breakdown: Record<string, number>;
  updated_at: string | null;
}