export interface ETLEntry {
  id: number;
  job_name: string;
  status: string;
  records_count?: number;
  error_msg?: string;
  start_time?: string;
  end_time?: string;
  created_at?: string;
}

export interface ETLStatusResponse {
  items: ETLEntry[];
  total?: number;
}
