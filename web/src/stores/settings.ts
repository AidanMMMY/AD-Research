import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type ColorConvention = 'china' | 'us';
export type HelpMode = 'novice' | 'pro';

interface SettingsState {
  /** Color convention: china=red up green down, us=green up red down */
  colorConvention: ColorConvention;
  setColorConvention: (c: ColorConvention) => void;
  /** Help mode: novice = long-form + examples + analogies; pro = concise. */
  mode: HelpMode;
  setMode: (m: HelpMode) => void;
  /**
   * K15: "学习模式"。默认关闭（与传统研报平台体验一致）。
   * 开启后：
   *  - StatCard 等数据组件下方会显示一行"这个数字是什么意思"小字解释
   *  - 与 `mode`(novice/pro) 正交：novice 控制 HelpPopover 内文长度，
   *    learningMode 控制"是否在每个数字旁边加教学说明"。
   */
  learningMode: boolean;
  setLearningMode: (v: boolean) => void;
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      colorConvention: 'china',
      mode: 'novice',
      learningMode: false,
      setColorConvention: (colorConvention) => set({ colorConvention }),
      setMode: (mode) => set({ mode }),
      setLearningMode: (learningMode) => set({ learningMode }),
    }),
    {
      name: 'settings-storage',
      // Persist preferences.  Older localStorage entries that don't include
      // `learningMode` will default to `false` thanks to zustand's merge
      // behaviour (undefined state fields fall back to the create() default).
      partialize: (state) => ({
        colorConvention: state.colorConvention,
        mode: state.mode,
        learningMode: state.learningMode,
      }),
      // Bump version so existing users get the new field cleanly migrated.
      version: 2,
    }
  )
);
