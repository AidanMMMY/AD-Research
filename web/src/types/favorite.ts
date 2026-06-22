export interface FavoriteItem {
  etf_code: string;
  etf_name?: string;
  category?: string;
  market?: string;
  created_at?: string;
}

export interface FavoriteListResponse {
  items: FavoriteItem[];
  count: number;
}

export interface FavoriteToggleResponse {
  etf_code: string;
  is_favorite: boolean;
  message: string;
}

export interface FavoriteStatusResponse {
  etf_code: string;
  is_favorite: boolean;
}
