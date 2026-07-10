import { useEffect, useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Select, Button, Skeleton, Modal, Empty, message, Popconfirm } from 'antd';
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
import { useSettingsStore } from '@/stores/settings';
import { SENTIMENT_LABELS } from '@/utils/sentiment';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

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

const SEARCH_DEBOUNCE_MS = 300;
const SEARCH_PAGE_SIZE = 50;

export default function ResearchNotes() {
  const mode = useSettingsStore((s) => s.mode);
  const [code, setCode] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [noteType, setNoteType] = useState<string | undefined>();
  const [modalNote, setModalNote] = useState<ResearchNote | null>(null);
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
      <PageHeader
        eyebrow="研究"
        title="研究笔记"
        description="AI 驱动的投研报告生成，支持日报、周报、财报分析等多种类型"
        data-onboard="research-notes"
      />
      <AISetupBanner />

      <Panel variant="default" className="phase5c-section">
        <div className="phase5c-form-row">
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
            suffixIcon={<SearchOutlined className="phase5c-icon-accent" />}
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
            className="phase5c-select--sm"
            value={noteType}
            options={NOTE_TYPE_OPTIONS}
            onChange={setNoteType}
          />
        </div>
      </Panel>

      <div className="phase5c-section">
        {isLoading ? (
          <Skeleton active paragraph={{ rows: 8 }} />
        ) : !notes?.length ? (
          <div className="phase5c-empty">
            <Empty
              description="暂无研报历史，输入或选择标的代码后点击「生成研报」开始 AI 分析"
            />
          </div>
        ) : (
          notes.map((note) => (
            <Panel
              key={note.id}
              variant="default"
              className="phase5c-research-card"
              padding="md"
            >
              <div onClick={() => setModalNote(note)}>
                <div className="phase5c-research-card__header">
                  <div className="phase5c-research-card__meta">
                    <InstrumentCodeTag
                      code={note.instrument_code}
                      name={note.name}
                      name_zh={note.name_zh}
                    />
                    <ThemeTag variant="default">
                      <HelpPopover termKey="note_type" mode={mode}>{note.note_type}</HelpPopover>
                    </ThemeTag>
                    {note.sentiment && (
                      <ThemeTag variant={SENTIMENT_VARIANTS[note.sentiment] || 'default'}>
                        {SENTIMENT_LABELS[note.sentiment] || note.sentiment}
                      </ThemeTag>
                    )}
                    {note.confidence && (
                      <span className="phase5c-detail-line">
                        <HelpPopover termKey="sentiment_confidence" mode={mode}>置信度</HelpPopover> {note.confidence}/10
                      </span>
                    )}
                  </div>
                  <div className="phase5c-research-card__actions">
                    <span className="phase5c-research-card__date">
                      {note.generated_at?.slice(0, 16) || note.created_at?.slice(0, 16)}
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
                        className="phase5c-research-card__delete"
                        onClick={(e) => e.stopPropagation()}
                      />
                    </Popconfirm>
                  </div>
                </div>
                {note.summary && (
                  <p className="phase5c-research-card__summary">
                    {note.summary}
                  </p>
                )}
                <div className="phase5c-research-card__more">
                  点击查看全文 →
                </div>
              </div>
            </Panel>
          ))
        )}
      </div>

      <Modal
        open={!!modalNote}
        onCancel={() => setModalNote(null)}
        footer={null}
        width={720}
        className="phase5c-markdown-modal"
      >
        {modalNote && (
          <div className="markdown-body phase5c-markdown-body">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {modalNote.content}
            </ReactMarkdown>
          </div>
        )}
      </Modal>
    </PageShell>
  );
}
