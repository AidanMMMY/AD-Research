import client from './client';
import type { ScanResult, ScanLog } from '@/types/scanner';

export const scannerApi = {
  triggerScan: () => client.post<ScanResult>('/etfs/scan'),
  getLogs: (limit?: number) =>
    client.get<ScanLog[]>('/etfs/scan/logs', { params: { limit } }),
};
