import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Select, Button, Input, Skeleton, Modal, Empty } from 'antd';
import { RobotOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { researchApi, ResearchNote } from '@/api/research';
import AISetupBanner from '@/components/AISetupBanner';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import ThemeTag, { ThemeTagVariant } from '@/components/ThemeTag';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const SENTIMENT_VARIANTS: Record<string, ThemeTagVariant> = {
  bullish: 'rise',
  bearish: 'fall',
  neutral: 'neutral',
};

const SENTIMENT_LABELS: Record<string, string> = {
  bullish: '看多',
  bearish: '看空',
  neutral: '中性',
};

const NOTE_TYPE_OPTIONS = [
  { label: '日报', value: 'daily_summary' },
  { label: '周报', value: 'weekly_review' },
  { label: '财报反应', value: 'earnings_reaction' },
  { label: '财报前瞻', value: 'earnings_preview' },
];

export default function ResearchNotes() {
  const [code, setCode] = useState('');
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const [noteType, setNoteType] = useState<string | undefined>();
  const [modalNote, setModalNote] = useState<ResearchNote | null>(null);
  const queryClient = useQueryClient();

  const { data: notes, isLoading } = useQuery({
    queryKey: ['research-notes', selectedCode, noteType],
    queryFn: () =>
      selectedCode
        ? researchApi.getNotes(selectedCode, noteType).then((r) => r.data)
        : Promise.resolve([]),
    enabled: !!selectedCode,
  });

  const generateMutation = useMutation({
    mutationFn: (code: string) => researchApi.generateNote(code),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research-notes', selectedCode] });
    },
  });

  const handleGenerate = () => {
    if (!code.trim()) return;
    setSelectedCode(code.trim().toUpperCase());
    generateMutation.mutate(code.trim().toUpperCase());
  };

  return (
    <PageShell maxWidth="wide">
      <PageHeader
        eyebrow="研究"
        title="研究笔记"
        description="AI 驱动的投研报告生成，支持日报、周报、财报分析等多种类型"
      />
      <AISetupBanner />

      <Panel variant="default" className="phase5c-section">
        <div className="phase5c-form-row">
          <Input
            placeholder="输入标的代码 (如 SPY.US, AAPL.US)"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            onPressEnter={handleGenerate}
            className="ad-form-row__grow"
            prefix={<ThunderboltOutlined className="phase5c-icon-accent" />}
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
        ) : !selectedCode ? (
          <div className="phase5c-empty">
            <Empty
              description="输入标的代码并点击「生成研报」开始 AI 分析"
            />
          </div>
        ) : !notes?.length ? (
          <div className="phase5c-empty">
            <Empty description={`暂无 ${selectedCode} 的研报`} />
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
                    <span className="phase5c-research-card__code">
                      {note.instrument_code}
                    </span>
                    <ThemeTag variant="default">{note.note_type}</ThemeTag>
                    {note.sentiment && (
                      <ThemeTag variant={SENTIMENT_VARIANTS[note.sentiment] || 'default'}>
                        {SENTIMENT_LABELS[note.sentiment] || note.sentiment}
                      </ThemeTag>
                    )}
                    {note.confidence && (
                      <span className="phase5c-detail-line">
                        置信度 {note.confidence}/10
                      </span>
                    )}
                  </div>
                  <span className="phase5c-research-card__date">
                    {note.generated_at?.slice(0, 16) || note.created_at?.slice(0, 16)}
                  </span>
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
