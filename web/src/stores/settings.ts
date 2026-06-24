import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type ColorConvention = 'china' | 'us';

interface SettingsState {
  /** Color convention: china=red up green down, us=green up red down */
  colorConvention: ColorConvention;
  setColorConvention: (c: ColorConvention) => void;
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      colorConvention: 'china',

      setColorConvention: (colorConvention) => set({ colorConvention }),
    }),
    {
      name: 'settings-storage',
      partialize: (state) => ({ colorConvention: state.colorConvention }),
    }
  )
);
