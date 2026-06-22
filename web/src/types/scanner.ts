export interface ETFChange {
  code: string;
  changes: Record<string, { old: string; new: string }>;
}

export interface ScanResultItem {
  code: string;
  name: string;
  market: string;
}

export interface ScanResult {
  success: boolean;
  new: ScanResultItem[];
  delisted: ScanResultItem[];
  changed: ETFChange[];
  scan_date: string;
  error?: string;
}

export interface ScanLog {
  id: number;
  scan_date: string;
  new_count: number;
  delisted_count: number;
  changed_count: number;
  status: string;
  error_msg?: string;
  created_at?: string;
}
