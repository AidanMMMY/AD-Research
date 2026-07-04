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
   * K15: "学习模式"。默认开启（2026-07-04 UX 整改：减少新用户因找不到
   * 头像菜单里开关而错失学习模式体验）。
   * 开启后：
   *  - StatCard 等数据组件下方会显示一行"这个数字是什么意思"小字解释
   *  - 与 `mode`(novice/pro) 正交：novice 控制 HelpPopover 内文长度，
   *    learningMode 控制"是否在每个数字旁边加教学说明"。
   * 想要恢复传统"关"的用户可以在右上角头像菜单里手动关闭。
   */
  learningMode: boolean;
  setLearningMode: (v: boolean) => void;
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      colorConvention: 'china',
      mode: 'novice',
      // 默认开启 learningMode，旧用户由于 zustand persist merge，
      // 若 localStorage 已存值（即使旧版本是 false）会保留旧值；新
      // 用户首次进入会拿到 true。
      learningMode: true,
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
