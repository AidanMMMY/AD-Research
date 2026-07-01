import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import client from './client';
import type {
  ListingEventDetail,
  ListingEventFacets,
  ListingEventListParams,
  ListingEventListResponse,
} from '@/types/listingEvent';

/** Build a query string from a typed ListingEventListParams object.
 *  Arrays are serialized via repeated keys (FastAPI list[str] support). */
function buildQueryString(params: ListingEventListParams | undefined): string {
  if (!params) return '';
  const parts: string[] = [];
  const append = (key: string, value: unknown) => {
    if (value === undefined || value === null || value === '') return;
    parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`);
  };
  const appendList = (key: string, values: string[] | undefined) => {
    if (!values || values.length === 0) return;
    for (const v of values) {
      parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(v)}`);
    }
  };
  append('page', params.page);
  append('page_size', params.page_size);
  appendList('board', params.boards);
  appendList('market', params.markets);
  appendList('status', params.statuses);
  append('industry', params.industry);
  append('start_date', params.start_date);
  append('end_date', params.end_date);
  append('date_field', params.date_field);
  append('q', params.q);
  append('sort_by', params.sort_by);
  append('sort_dir', params.sort_dir);
  return parts.length === 0 ? '' : `?${parts.join('&')}`;
}

export const listingEventApi = {
  list: (params?: ListingEventListParams) =>
    client.get<ListingEventListResponse>(`/listing-events${buildQueryString(params)}`),
  get: (id: number) => client.get<ListingEventDetail>(`/listing-events/${id}`),
  getFacets: () => client.get<ListingEventFacets>('/listing-events/facets'),
  refresh: () => client.post<{ status: string; records: string }>('/listing-events/refresh'),
};

export function useListingEventList(params?: ListingEventListParams) {
  return useQuery({
    queryKey: ['listing-events', 'list', params],
    queryFn: async () => {
      const res = await listingEventApi.list(params);
      return res.data;
    },
    staleTime: 30_000,
  });
}

export function useListingEventDetail(id: number | null) {
  return useQuery({
    queryKey: ['listing-events', 'detail', id],
    queryFn: async () => {
      if (id == null) return null;
      const res = await listingEventApi.get(id);
      return res.data;
    },
    enabled: id != null,
    staleTime: 60_000,
  });
}

export function useListingEventFacets() {
  return useQuery({
    queryKey: ['listing-events', 'facets'],
    queryFn: async () => {
      const res = await listingEventApi.getFacets();
      return res.data;
    },
    staleTime: 300_000,
  });
}

export function useRefreshListingEvents() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const res = await listingEventApi.refresh();
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['listing-events'] });
    },
  });
}