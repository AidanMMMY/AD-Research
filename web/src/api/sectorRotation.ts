import client from './client';

export interface SectorPerformance {
  category: string;
  count: number;
  return_1m: number;
  return_3m: number;
  sharpe_1y: number;
  volatility_20d: number;
  rsi14: number;
  relative_strength_1m: number;
  relative_strength_3m: number;
  momentum_rank: number;
}

export interface RotationSignal {
  category: string;
  type: string;
  message: string;
  current_rank: number;
  previous_rank: number;
}

export interface SectorRotationData {
  trade_date: string;
  sectors: SectorPerformance[];
  market_avg: {
    return_1m: number;
    return_3m: number;
    sharpe_1y: number;
  };
  rotation_signals: RotationSignal[];
}

export const sectorRotationApi = {
  analyze: (trade_date?: string, window_weeks?: number) =>
    client.get<SectorRotationData>('/analysis/sector-rotation', {
      params: { trade_date, window_weeks },
    }),
  sectors: () => client.get<{ items: { category: string; count: number }[] }>('/analysis/sector-rotation/sectors'),
};
