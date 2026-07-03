import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface OnboardingState {
  /** Whether the user has finished (or skipped) the onboarding tour. */
  completed: boolean;
  /** Set to true when the tour should be (re)opened on the next dashboard visit. */
  reopen: boolean;
  setCompleted: (v: boolean) => void;
  triggerReopen: () => void;
  clearReopen: () => void;
}

export const useOnboardingStore = create<OnboardingState>()(
  persist(
    (set) => ({
      completed: false,
      reopen: false,
      setCompleted: (completed) => set({ completed, reopen: false }),
      triggerReopen: () => set({ reopen: true }),
      clearReopen: () => set({ reopen: false }),
    }),
    {
      name: 'ad-research-onboarding-storage',
      partialize: (state) => ({ completed: state.completed }),
    }
  )
);