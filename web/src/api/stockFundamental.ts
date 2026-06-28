import client from './client';
import type { StockFundamental } from '../types/stockFundamental';

export const stockFundamentalApi = {
  /** Get latest valuation + income data for an A-share stock. */
  get: (code: string) =>
    client.get<StockFundamental>(`/stock-fundamentals/${code}`),
};
