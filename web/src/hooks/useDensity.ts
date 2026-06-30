import { useEffect, useState } from 'react';

export type Density = 'dense' | 'comfortable' | 'spacious';

const STORAGE_KEY = 'ad-density';
const DEFAULT_DENSITY: Density = 'comfortable';

function readDensity(): Density {
  if (typeof window === 'undefined') return DEFAULT_DENSITY;
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    if (v === 'dense' || v === 'comfortable' || v === 'spacious') return v;
  } catch {
    // ignore
  }
  return DEFAULT_DENSITY;
}

export function useDensity(): { density: Density; setDensity: (d: Density) => void } {
  const [density, setDensityState] = useState<Density>(() => readDensity());

  useEffect(() => {
    if (typeof document === 'undefined') return;
    const classes = ['ad-density-dense', 'ad-density-comfortable', 'ad-density-spacious'];
    document.body.classList.remove(...classes);
    document.body.classList.add(`ad-density-${density}`);
  }, [density]);

  const setDensity = (d: Density) => {
    setDensityState(d);
    try {
      window.localStorage.setItem(STORAGE_KEY, d);
    } catch {
      // ignore
    }
  };

  return { density, setDensity };
}