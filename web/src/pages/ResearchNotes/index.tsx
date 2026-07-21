import { useEffect, useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Select, Button, Modal, message, Popconfirm } from 'antd';
import { RobotOutlined, SearchOutlined, DeleteOutlined } from '@ant-design/icons';
import './styles.css';
import { researchApi, ResearchNote } from '@/api/research';
import { useInstrumentList } from '@/hooks/useInstrumentList';
import type { InstrumentInfo } from '@/types/instrument';
import AISetupBanner from '@/components/AISetupBanner';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import ThemeTag, { ThemeTagVariant } from '@/components/ThemeTag';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import HelpPopover from '@/components/HelpPopover';
import EmptyState from '@/components/EmptyState';
import LoadingBlock from '@/components/LoadingBlock';
import { useSettingsStore } from '@/stores/settings';
import { SENTIMENT_LABELS } from '@/utils/sentiment';
import { formatDateTime } from '@/utils/datetime';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/**
 * Apple Design fixes scoped to this page:
 * 1. Pointer-down feedback — research cards open a modal on click but
 *    previously had no touch-down state; they now highlight and press
 *    (subtle scale) on :active, per Apple's Response principle.
 * 2. The delete affordance gets the same press treatment.
 * 3. Reduced-motion users get no transform/transition at all.
 */
const RESEARCH_NOTES_PAGE_STYLE = `
.ad-research-card {
  transform-origin: center;
  transition: transform var(--transition-spring-fast, 200ms var(--ease-spring)),
    background var(--transition-spring-fast, 200ms var(--ease-spring));
}
.ad-research-card:active {
  background: var(--bg-active);
  transform: scale(var(--press-scale-subtle, 0.99));
}
.ad-research-card__delete {
  transition: transform var(--transition-spring-fast, 200ms var(--ease-spring));
}
.ad-research-card__delete:active {
  transform: scale(var(--press-scale, 0.97));
}
/* Full-note modal spring — anchored to the row that opened it via
   inline CSS variables on the modal wrap (modalOriginX/modalOriginY). */
.ant-modal.ad-research-note-modal .ant-modal-content {
  animation: research-note-modal-spring var(--transition-spring) both;
  transform-origin: var(--modal-origin-x, 50%) var(--modal-origin-y, 50%);
}
@keyframes research-note-modal-spring {
  from { opacity: 0; transform: scale(0.96); }
  to   { opacity: 1; transform: scale(1); }
}
@media (prefers-reduced-motion: reduce) {
  .ad-research-card,
  .ad-research-card__delete {
    transition: none;
    transform: none;
  }
  .ant-modal.ad-research-note-modal .ant-modal-content {
    animation: none;
    transform: none;
  }
}
`;

const SENTIMENT_VARIANTS: Record<string, ThemeTagVariant> = {
  bullish: 'rise',
  bearish: 'fall',
  neutral: 'neutral',
};

const NOTE_TYPE_OPTIONS = [
  { label: '日报', value: 'daily_summary' },
  { label: '周报', value: 'weekly_review' },
  { label: '财报反应', value: 'earnings_reaction' },
  { label: '财报前瞻', value: 'earnings_preview' },
];

/** Chinese labels for the raw note_type enum stored on each note. */
const NOTE_TYPE_LABELS: Record<string, string> = Object.fromEntries(
  NOTE_TYPE_OPTIONS.map((o) => [o.value, o.label]),
);

const SEARCH_DEBOUNCE_MS = 300;
const SEARCH_PAGE_SIZE = 50;

export default function ResearchNotes() {
  const mode = useSettingsStore((s) => s.mode);
  const [code, setCode] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [noteType, setNoteType] = useState<string | undefined>();
  const [modalNote, setModalNote] = useState<ResearchNote | null>(null);
  /* Apple "Spatial consistency": anchor the full-note modal to the
     triggering card via CSS variables on the modal wrap. */
  const [modalAnchor, setModalAnchor] = useState<{ x: number; y: number } | null>(null);
  const queryClient = useQueryClient();

  // Debounce the search text so we don't hammer the backend on every keystroke.
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput.trim());
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const { data: notes, isLoading } = useQuery({
    queryKey: ['research-notes', 'history', noteType],
    queryFn: () => researchApi.getMyNotes(noteType).then((r) => r.data),
  });

  const { data: instrumentSearch, isFetching: isSearchingInstruments } = useInstrumentList({
    search: debouncedSearch || undefined,
    page_size: SEARCH_PAGE_SIZE,
  });

  const instrumentOptions = useMemo(
    () =>
      (instrumentSearch?.items || []).map((item: InstrumentInfo) => ({
        label: `${item.code} ${item.name}`,
        value: item.code,
      })),
    [instrumentSearch],
  );

  const generateMutation = useMutation({
    mutationFn: (code: string) => researchApi.generateNote(code),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research-notes', 'history'] });
    },
    onError: (err: any) => {
      message.error(err?.response?.data?.detail || '生成研报失败');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => researchApi.deleteNote(id),
    onSuccess: (_data, id) => {
      if (modalNote?.id === id) {
        setModalNote(null);
      }
      queryClient.invalidateQueries({ queryKey: ['research-notes', 'history'] });
      message.success('已删除');
    },
    onError: () => {
      message.error('删除失败');
    },
  });

  const triggerGenerate = (targetCode: string) => {
    const normalized = targetCode.trim().toUpperCase();
    if (!normalized) return;
    setCode(normalized);
    generateMutation.mutate(normalized);
  };

  const handleGenerate = () => {
    triggerGenerate(code);
  };

  const handleSelectInstrument = (value: string) => {
    triggerGenerate(value);
    // Clear the search field so the dropdown resets next time it opens.
    setSearchInput('');
  };

  return (
    <PageShell maxWidth="wide">
      <style>{RESEARCH_NOTES_PAGE_STYLE}</style>
      <PageHeader
        eyebrow="研究"
        title="研究笔记"
        description="AI 驱动的投研报告生成，支持日报、周报、财报分析等多种类型"
        data-onboard="research-notes"
      />
      <AISetupBanner />

      <Panel variant="default" className="ad-section">
        <div className="ad-form-row">
          <Select
            showSearch
            filterOption={false}
            placeholder="搜索标的代码或名称 (如 SPY / AAPL / 沪深300)"
            value={code || undefined}
            searchValue={searchInput}
            onSearch={setSearchInput}
            onChange={handleSelectInstrument}
            onInputKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                handleGenerate();
              }
            }}
            notFoundContent={isSearchingInstruments ? '搜索中...' : '未找到匹配的标的'}
            options={instrumentOptions}
            className="ad-form-row__grow"
            suffixIcon={<SearchOutlined className="ad-icon-accent" />}
            optionFilterProp="label"
            listHeight={320}
          />
          <Button
            type="primary"
            icon={<RobotOutlined />}
            loading={generateMutation.isPending}
            onClick={handleGenerate}
          >
            生成研报
          </Button>
          <Select
            placeholder="类型筛选"
            allowClear
            className="ad-select--sm"
            value={noteType}
            options={NOTE_TYPE_OPTIONS}
            onChange={setNoteType}
          />
        </div>
      </Panel>

      <div className="ad-section">
        {isLoading ? (
          <LoadingBlock size="lg" />
        ) : !notes?.length ? (
          <div className="ad-empty">
            <EmptyState
              title="暂无研报历史，输入或选择标的代码后点击「生成研报」开始 AI 分析"
            />
          </div>
        ) : (
          notes.map((note) => (
            <Panel
              key={note.id}
              variant="default"
              className="ad-research-card"
              padding="md"
            >
              <div
                role="button"
                tabIndex={0}
                aria-label={`打开研报 ${note.name ?? note.instrument_code}`}
                onClick={(e) => {
                  /* Apple "Spatial consistency": capture the card's
                     viewport center so the modal scales out from it. */
                  const target = e.currentTarget as HTMLElement | null;
                  if (target) {
                    const rect = target.getBoundingClientRect();
                    setModalAnchor({
                      x: rect.left + rect.width / 2,
                      y: rect.top + rect.height / 2,
                    });
                  }
                  setModalNote(note);
                }}
                onKeyDown={(e) => {
                  /* Apple "Agency": same affordance for keyboard users. */
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    const target = e.currentTarget as HTMLElement | null;
                    if (target) {
                      const rect = target.getBoundingClientRect();
                      setModalAnchor({
                        x: rect.left + rect.width / 2,
                        y: rect.top + rect.height / 2,
                      });
                    }
                    setModalNote(note);
                  }
                }}
              >
                <div className="ad-research-card__header">
                  <div className="ad-research-card__meta">
                    <InstrumentCodeTag
                      code={note.instrument_code}
                      name={note.name}
                      name_zh={note.name_zh}
                    />
                    <ThemeTag variant="default">
                      <HelpPopover termKey="note_type" mode={mode}>{NOTE_TYPE_LABELS[note.note_type] ?? note.note_type}</HelpPopover>
                    </ThemeTag>
                    {note.sentiment && (
                      <ThemeTag variant={SENTIMENT_VARIANTS[note.sentiment] || 'default'}>
                        {SENTIMENT_LABELS[note.sentiment] || note.sentiment}
                      </ThemeTag>
                    )}
                    {note.confidence && (
                      <span className="ad-detail-line">
                        <HelpPopover termKey="sentiment_confidence" mode={mode}>置信度</HelpPopover> {note.confidence}/10
                      </span>
                    )}
                  </div>
                  <div className="ad-research-card__actions">
                    <span className="ad-research-card__date">
                      {formatDateTime(note.generated_at ?? note.created_at, 'YYYY-MM-DD HH:mm', '')}
                    </span>
                    <Popconfirm
                      title="删除此研报？"
                      onConfirm={(e) => {
                        e?.stopPropagation();
                        deleteMutation.mutate(note.id);
                      }}
                      onCancel={(e) => e?.stopPropagation()}
                    >
                      <DeleteOutlined
                        role="button"
                        tabIndex={0}
                        aria-label="删除研报"
                        className="ad-research-card__delete"
                        onClick={(e) => e.stopPropagation()}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            e.stopPropagation();
                          }
                        }}
                      />
                    </Popconfirm>
                  </div>
                </div>
                {note.summary && (
                  <p className="ad-research-card__summary">
                    {note.summary}
                  </p>
                )}
                <div className="ad-research-card__more">
                  点击查看全文 →
                </div>
              </div>
            </Panel>
          ))
        )}
      </div>

      <Modal
        open={!!modalNote}
        onCancel={() => {
          setModalNote(null);
          setModalAnchor(null);
        }}
        afterClose={() => setModalAnchor(null)}
        footer={null}
        width={720}
        className="ad-research-note-modal"
        wrapClassName="ad-research-note-modal-wrap"
        style={
          modalAnchor
            ? ({
                ['--modal-origin-x' as string]: `${modalAnchor.x}px`,
                ['--modal-origin-y' as string]: `${modalAnchor.y}px`,
              } as CSSProperties)
            : undefined
        }
      >
        {modalNote && (
          <div className="markdown-body ad-markdown-body">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {modalNote.content}
            </ReactMarkdown>
          </div>
        )}
      </Modal>
    </PageShell>
  );
}
