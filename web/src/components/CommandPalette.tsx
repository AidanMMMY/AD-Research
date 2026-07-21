import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { Modal, Input, type InputRef } from 'antd';
import {
  SearchOutlined,
  FileTextOutlined,
  ReadOutlined,
  LineChartOutlined,
  ClockCircleOutlined,
  EnterOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useFocusRestore } from '@/hooks/useFocusRestore';
import {
  globalSearch,
  type Suggestion,
  type SuggestionType,
} from '@/api/globalSearch';
import './CommandPalette.css';

const RECENT_KEY = 'ad-research:command-palette:recent';
const MAX_RECENT = 6;
const DEBOUNCE_MS = 250;

/* ---------------------------------------------------------------------------
 * localStorage-backed "recent" list
 * ------------------------------------------------------------------------- */
function loadRecent(): Suggestion[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.slice(0, MAX_RECENT) : [];
  } catch {
    return [];
  }
}

function pushRecent(item: Suggestion): void {
  try {
    const next = [item, ...loadRecent().filter((r) => r.href !== item.href)].slice(
      0,
      MAX_RECENT
    );
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    /* swallow — storage may be unavailable / full */
  }
}

/* ---------------------------------------------------------------------------
 * Debounce hook — 250ms on the query so type-ahead doesn't thrash.
 * ------------------------------------------------------------------------- */
function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

const TYPE_ICON: Record<SuggestionType | 'recent', React.ReactNode> = {
  page: <LineChartOutlined />,
  instrument: <FileTextOutlined />,
  news: <ReadOutlined />,
  recent: <ClockCircleOutlined />,
};

const TYPE_LABEL: Record<SuggestionType, string> = {
  page: '页面',
  instrument: '标的',
  news: '资讯',
};

interface PaletteRow {
  sectionKey: string;
  sectionTitle: string;
  item: Suggestion;
  index: number;
  isFirstInSection: boolean;
}

export interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Command Palette (⌘K / Ctrl+K).
 *
 * Two-pane modal: a search input on top, grouped results below. Renders the
 * page registry (filtered by name / path) plus a "recent" list from
 * localStorage. Keyboard: ↑/↓ to move, Enter to select, Esc to close.
 * Focus is restored to the opening trigger on close via useFocusRestore.
 */
export default function CommandPalette({ open, onClose }: CommandPaletteProps) {
  const navigate = useNavigate();
  const inputRef = useRef<InputRef>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const [query, setQuery] = useState('');
  const debounced = useDebounced(query, DEBOUNCE_MS);
  const [results, setResults] = useState<Suggestion[]>([]);
  const [recent, setRecent] = useState<Suggestion[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);

  // WCAG 2.4.3 — return focus to the ⌘K trigger when the palette closes.
  useFocusRestore(open);

  // On open: reset state, refresh recents, and focus the input next tick.
  useEffect(() => {
    if (!open) return;
    setQuery('');
    setActiveIndex(0);
    setRecent(loadRecent());
    const t = setTimeout(() => inputRef.current?.focus({ cursor: 'end' }), 20);
    return () => clearTimeout(t);
  }, [open]);

  // Query the aggregate search whenever the debounced query changes.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    globalSearch(debounced).then((res) => {
      if (!cancelled) {
        setResults(res.data);
        setActiveIndex(0);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [debounced, open]);

  const hasQuery = query.trim().length > 0;

  // Build the ordered sections: recent (only when idle) → pages → instruments → news.
  const rows = useMemo<PaletteRow[]>(() => {
    const sections: { key: string; title: string; items: Suggestion[] }[] = [];

    if (!hasQuery && recent.length > 0) {
      sections.push({ key: 'recent', title: '最近访问', items: recent });
    }
    const pages = results.filter((r) => r.type === 'page');
    const instruments = results.filter((r) => r.type === 'instrument');
    const news = results.filter((r) => r.type === 'news');
    if (pages.length) sections.push({ key: 'page', title: '页面', items: pages });
    if (instruments.length)
      sections.push({ key: 'instrument', title: '标的', items: instruments });
    if (news.length) sections.push({ key: 'news', title: '资讯', items: news });

    const out: PaletteRow[] = [];
    let i = 0;
    for (const sec of sections) {
      sec.items.forEach((item, j) => {
        out.push({
          sectionKey: sec.key,
          sectionTitle: sec.title,
          item,
          index: i,
          isFirstInSection: j === 0,
        });
        i += 1;
      });
    }
    return out;
  }, [hasQuery, recent, results]);

  const flat = useMemo(() => rows.map((r) => r.item), [rows]);

  // Keep the active row within bounds when the result set shrinks.
  useEffect(() => {
    if (activeIndex > flat.length - 1) setActiveIndex(Math.max(0, flat.length - 1));
  }, [flat.length, activeIndex]);

  // Scroll the active row into view on keyboard navigation.
  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>('.cmdk__item.is-active');
    el?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex, rows]);

  const handleSelect = useCallback(
    (item: Suggestion) => {
      pushRecent(item);
      onClose();
      navigate(item.href);
    },
    [navigate, onClose]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveIndex((i) => Math.min(i + 1, flat.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const item = flat[activeIndex];
        if (item) handleSelect(item);
      }
      // Esc is handled by the Modal (onCancel).
    },
    [flat, activeIndex, handleSelect]
  );

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      closable={false}
      destroyOnClose
      maskClosable
      width={620}
      className="cmdk-modal"
      styles={{ body: { padding: 0 }, content: { padding: 0, overflow: 'hidden' } }}
    >
      <div className="cmdk" onKeyDown={handleKeyDown}>
        <div className="cmdk__input-row">
          <SearchOutlined className="cmdk__input-icon" aria-hidden="true" />
          <Input
            ref={inputRef}
            variant="borderless"
            className="cmdk__input"
            placeholder="搜索页面、标的、资讯…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="命令面板搜索"
            role="combobox"
            aria-expanded
            aria-haspopup="listbox"
            aria-controls="cmdk-listbox"
            aria-activedescendant={
              activeIndex >= 0 && activeIndex < rows.length ? `cmdk-option-${activeIndex}` : undefined
            }
          />
          <kbd className="cmdk__esc">Esc</kbd>
        </div>

        <div className="cmdk__results" id="cmdk-listbox" role="listbox" ref={listRef}>
          {rows.length === 0 ? (
            <div className="cmdk__empty">没有匹配结果</div>
          ) : (
            rows.map((row) => {
              const active = row.index === activeIndex;
              const icon =
                row.sectionKey === 'recent'
                  ? TYPE_ICON.recent
                  : TYPE_ICON[row.item.type];
              return (
                <React.Fragment key={`${row.sectionKey}-${row.item.type}-${row.item.id}`}>
                  {row.isFirstInSection && (
                    <div className="cmdk__section-title">{row.sectionTitle}</div>
                  )}
                  <div
                    role="option"
                    id={`cmdk-option-${row.index}`}
                    tabIndex={-1}
                    aria-selected={active}
                    className={`cmdk__item ${active ? 'is-active' : ''}`}
                    onMouseMove={() => setActiveIndex(row.index)}
                    onClick={() => handleSelect(row.item)}
                  >
                    <span className="cmdk__item-icon" aria-hidden="true">
                      {icon}
                    </span>
                    <span className="cmdk__item-text">
                      <span className="cmdk__item-title">{row.item.title}</span>
                      {row.item.subtitle && (
                        <span className="cmdk__item-subtitle">{row.item.subtitle}</span>
                      )}
                    </span>
                    {row.sectionKey !== 'recent' && (
                      <span className="cmdk__item-type">{TYPE_LABEL[row.item.type]}</span>
                    )}
                    {active && (
                      <span className="cmdk__item-enter" aria-hidden="true">
                        <EnterOutlined />
                      </span>
                    )}
                  </div>
                </React.Fragment>
              );
            })
          )}
        </div>

        <div className="cmdk__footer">
          <span><kbd>↑</kbd><kbd>↓</kbd> 导航</span>
          <span><kbd>↵</kbd> 选择</span>
          <span><kbd>Esc</kbd> 关闭</span>
        </div>
      </div>
    </Modal>
  );
}
