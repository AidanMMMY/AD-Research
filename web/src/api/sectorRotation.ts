import client from './client';
import type {
  SectorListData,
  SectorRotationData,
} from '@/types/sector_rotation';

/**
 * Re-export the canonical types so feature code that historically
 * imported `SectorPerformance` / `SectorRotationData` from this module
 * keeps working.
 */
export type {
  MarketAverage,
  RotationSignal,
  SectorListData,
  SectorListItem,
  SectorPerformance,
  SectorRotationData,
  SectorScope,
} from '@/types/sector_rotation';

export const sectorRotationApi = {
  analyze: (trade_date?: string, window_weeks?: number) =>
    client.get<SectorRotationData>('/sector-rotation', {
      params: { trade_date, window_weeks },
    }),
  sectors: () => client.get<SectorListData>('/sector-rotation/sectors'),
};