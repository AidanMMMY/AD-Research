import { create } from 'zustand';

/**
 * Global AI-chat sheet state (方向 D, 2026-07-29).
 *
 * The mobile AI assistant lives in a global BottomSheet that can be
 * summoned from any page without leaving context. Two kinds of state
 * must survive the sheet closing (the sheet unmounts its children on
 * close):
 *
 *  - ``activeSession`` — which conversation the user is in. Hoisted here
 *    so the /chat page and the sheet share the same pointer; messages
 *    themselves stay in the react-query cache keyed by session id.
 *  - ``draft`` — the unsent input text. Closing the sheet mid-typing
 *    must not eat the draft.
 *
 * Deliberately NOT persisted to localStorage: the sheet starts closed on
 * every fresh page load, and resurrecting a stale session pointer across
 * days would be more surprising than helpful.
 */
interface AIChatSheetState {
  /** Whether the global mobile chat sheet is open. */
  sheetOpen: boolean;
  openSheet: () => void;
  closeSheet: () => void;
  /** Active chat session id, shared between /chat page and the sheet. */
  activeSession: number | null;
  setActiveSession: (id: number | null) => void;
  /** Unsent composer text (survives sheet close/open). */
  draft: string;
  setDraft: (v: string) => void;
}

export const useAIChatSheetStore = create<AIChatSheetState>()((set) => ({
  sheetOpen: false,
  openSheet: () => set({ sheetOpen: true }),
  closeSheet: () => set({ sheetOpen: false }),
  activeSession: null,
  setActiveSession: (activeSession) => set({ activeSession }),
  draft: '',
  setDraft: (draft) => set({ draft }),
}));
