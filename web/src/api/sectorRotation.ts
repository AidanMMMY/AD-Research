import client from './client';
import type {
  SectorClassification,
  SectorConstituentsData,
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
  SectorClassification,
  SectorConstituent,
  SectorConstituentsData,
  SectorListData,
  SectorListItem,
  SectorPerformance,
  SectorRotationData,
  SectorScope,
} from '@/types/sector_rotation';

export const sectorRotationApi = {
  analyze: (
    trade_date?: string,
    window_weeks?: number,
    classification?: SectorClassification,
  ) =>
    client.get<SectorRotationData>('/sector-rotation', {
      params: { trade_date, window_weeks, classification },
    }),
  sectors: (classification?: SectorClassification) =>
    client.get<SectorListData>('/sector-rotation/sectors', {
      params: { classification },
    }),
  /**
   * Top-N constituents for a single GICS sector. Returns STOCK + ETF
   * instruments ranked by market cap (STOCK) or fund size (ETF).
   *
   * @param sector  GICS sector name (level-1). Must match one of the
   *                strings returned by ``sectors()``.
   * @param params  Optional: ``top_n`` (1-200, default 20) and
   *                ``trade_date`` (ISO date, default = latest).
   */
  constituents: (
    sector: string,
    params?: { top_n?: number; trade_date?: string; classification?: SectorClassification },
  ) =>
    client.get<SectorConstituentsData>(
      `/sector-rotation/sectors/${encodeURIComponent(sector)}/constituents`,
      { params },
    ),
};