export interface DeploymentRun {
  id: number;
  run_number: number;
  status: string;
  conclusion: string | null;
  head_branch: string;
  head_sha: string;
  display_title: string;
  actor_login: string;
  created_at: string;
  updated_at: string;
  duration_seconds: number;
  html_url: string;
}

export interface ContainerStats {
  name: string;
  status: string;
  state: string;
  image: string;
  cpu_percent: number;
  memory_usage: string;
  memory_limit: string;
  memory_percent: number;
  uptime: string;
}

export interface ServerHealth {
  containers: ContainerStats[];
  timestamp: string;
}

export interface LogLine {
  timestamp: string;
  container: string;
  message: string;
}
