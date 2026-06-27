import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface CryptoFilterState {
  search: string;
  category: string | undefined;
  sortBy: string;
  sortOrder: string;
  setSearch: (v: string) => void;
  setCategory: (v: string | undefined) => void;
  setSort: (by: string, order: string) => void;
  resetFilters: () => void;
}

const DEFAULTS = {
  search: '',
  category: undefined as string | undefined,
  sortBy: 'name',
  sortOrder: 'asc',
};

export const useCryptoStore = create<CryptoFilterState>()(
  persist(
    (set) => ({
      ...DEFAULTS,
      setSearch: (search) => set({ search }),
      setCategory: (category) => set({ category }),
      setSort: (sortBy, sortOrder) => set({ sortBy, sortOrder }),
      resetFilters: () => set(DEFAULTS),
    }),
    {
      name: 'crypto-filters',
      partialize: (state) => ({
        category: state.category,
        sortBy: state.sortBy,
        sortOrder: state.sortOrder,
      }),
    },
  ),
);
