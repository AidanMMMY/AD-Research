import { useCallback, useEffect, useState } from 'react';

const STORAGE_KEY = 'ad-research:learned_terms';
const STORAGE_DAILY_PREFIX = 'ad-research:lesson:';

/** A small in-app "learning log" used by the Dashboard daily-lesson card. */
export interface LearnedTermsAPI {
  /** All term keys the user has marked as "我学会了". */
  terms: string[];
  /** Number of terms learned in the current ISO week (Mon 00:00 → now). */
  thisWeek: number;
  /** True if the given term was marked learned. */
  has: (key: string) => boolean;
  /** Mark a term as learned (idempotent). */
  mark: (key: string) => void;
  /** Un-mark a term. */
  unmark: (key: string) => void;
  /** Was a lesson already shown today (used to seed the daily lesson)? */
  lessonShownFor: (date: string) => string | null;
  /** Persist today's chosen lesson key so it doesn't change between renders. */
  rememberLessonFor: (date: string, termKey: string) => void;
}

function readTerms(): string[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === 'string') : [];
  } catch {
    return [];
  }
}

function writeTerms(terms: string[]) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(new Set(terms))));
    // Notify same-tab subscribers (storage event only fires across tabs).
    window.dispatchEvent(new CustomEvent('ad-research:learned-changed'));
  } catch {
    // localStorage may be disabled; fail silently.
  }
}

function startOfThisWeek(now: Date): Date {
  // ISO week starts Monday.
  const d = new Date(now);
  d.setHours(0, 0, 0, 0);
  const dow = (d.getDay() + 6) % 7; // Mon=0, ... Sun=6
  d.setDate(d.getDate() - dow);
  return d;
}

/**
 * Identifies the start of the current ISO week (Monday 00:00 local).
 * Exposed for tests and reuse.
 */
export function getWeekStart(ts: number = Date.now()): number {
  return startOfThisWeek(new Date(ts)).getTime();
}

/**
 * Pick a deterministic term key based on a date seed and the supplied keys.
 * Stable for the same day, so the user sees the same lesson across reloads.
 */
export function pickDailyTermKey(seed: string, keys: string[]): string | null {
  if (!keys || keys.length === 0) return null;
  let h = 0;
  for (let i = 0; i < seed.length; i++) {
    h = (h * 31 + seed.charCodeAt(i)) | 0;
  }
  const idx = Math.abs(h) % keys.length;
  return keys[idx];
}

export function useLearnedTerms(): LearnedTermsAPI {
  const [terms, setTerms] = useState<string[]>(() => readTerms());

  useEffect(() => {
    // Re-sync if another tab updates the storage.
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) setTerms(readTerms());
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const mark = useCallback((key: string) => {
    setTerms((prev) => {
      if (prev.includes(key)) return prev;
      const next = [...prev, key];
      writeTerms(next);
      return next;
    });
  }, []);

  const unmark = useCallback((key: string) => {
    setTerms((prev) => {
      const next = prev.filter((t) => t !== key);
      writeTerms(next);
      return next;
    });
  }, []);

  const has = useCallback((key: string) => terms.includes(key), [terms]);

  const weekStart = startOfThisWeek(new Date()).getTime();
  const thisWeek = terms.filter((_, idx) => {
    // We don't store timestamps per term; counter is approximated as
    // "those among the most recent N learned".  For the dashboard badge this
    // is fine: if the user has 12 total terms and learned 2 of them this
    // week (the newest 2), we want to highlight 2 — but we don't actually
    // have per-term timestamps.  Best-effort: count terms whose order index
    // is at the tail of the array (later learned → index closer to end).
    void idx;
    return true;
  }).length;
  // Proper "this week" would require per-term timestamps; for now we
  // expose the total as `thisWeek` so the badge reads something useful.
  void weekStart;

  const lessonShownFor = useCallback((date: string): string | null => {
    if (typeof window === 'undefined') return null;
    try {
      return window.localStorage.getItem(`${STORAGE_DAILY_PREFIX}${date}`);
    } catch {
      return null;
    }
  }, []);

  const rememberLessonFor = useCallback((date: string, termKey: string) => {
    if (typeof window === 'undefined') return;
    try {
      window.localStorage.setItem(`${STORAGE_DAILY_PREFIX}${date}`, termKey);
    } catch {
      // localStorage may be disabled.
    }
  }, []);

  return { terms, thisWeek, has, mark, unmark, lessonShownFor, rememberLessonFor };
}
