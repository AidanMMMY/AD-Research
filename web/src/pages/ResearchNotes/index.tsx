import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Select, Button, Input, Skeleton, Modal, Empty } from 'antd';
import { RobotOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { researchApi, ResearchNote } from '@/api/research';
import AISetupBanner from "@/components/AISetupBanner";
import GlassCard from '@/components/GlassCard';
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
    <div>
      <h1 style={{ fontSize: 'var(--text-h1-size)', fontWeight: 500, color: 'var(--text-primary)', margin: '0 0 8px', letterSpacing: '-0.03em' }}>研究笔记</h1>
      <p style={{ margin: '0 0 32px', color: 'var(--text-tertiary)', fontSize: 'var(--text-body-size)' }}>AI 驱动的投研报告生成，支持日报、周报、财报分析等多种类型</p>
      <AISetupBanner />
      <GlassCard>
        <div style={{ display: 'flex', gap: 'var(--space-sm)', flexWrap: 'wrap', alignItems: 'center' }}>
          <Input
            placeholder="输入标的代码 (如 SPY.US, AAPL.US)"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            onPressEnter={handleGenerate}
            style={{ flex: 1, minWidth: 200 }}
            prefix={<ThunderboltOutlined style={{ color: 'var(--accent)' }} />}
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
            style={{ width: 140 }}
            value={noteType}
            options={[
              { label: '日报', value: 'daily_summary' },
              { label: '周报', value: 'weekly_review' },
              { label: '财报反应', value: 'earnings_reaction' },
              { label: '财报前瞻', value: 'earnings_preview' },
            ]}
            onChange={setNoteType}
          />
        </div>
      </GlassCard>

      <div style={{ marginTop: 'var(--space-lg)' }}>
        {isLoading ? (
          <Skeleton active paragraph={{ rows: 8 }} />
        ) : !selectedCode ? (
          <Empty
            description="输入标的代码并点击「生成研报」开始 AI 分析"
            style={{ marginTop: 60 }}
          />
        ) : !notes?.length ? (
          <Empty description={`暂无 ${selectedCode} 的研报`} style={{ marginTop: 60 }} />
        ) : (
          notes.map((note) => (
            <GlassCard key={note.id} style={{ marginBottom: 'var(--space-md)' }}>
              <div
                style={{ cursor: 'pointer' }}
                onClick={() => setModalNote(note)}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--space-xs)' }}>
                  <div style={{ display: 'flex', gap: 'var(--space-xs)', alignItems: 'center', flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--accent)', fontFamily: "'SF Mono', monospace" }}>
                      {note.instrument_code}
                    </span>
                    <ThemeTag variant="default">{note.note_type}</ThemeTag>
                    {note.sentiment && (
                      <ThemeTag variant={SENTIMENT_VARIANTS[note.sentiment] || 'default'}>
                        {SENTIMENT_LABELS[note.sentiment] || note.sentiment}
                      </ThemeTag>
                    )}
                    {note.confidence && (
                      <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)' }}>
                        置信度 {note.confidence}/10
                      </span>
                    )}
                  </div>
                  <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)', whiteSpace: 'nowrap' }}>
                    {note.generated_at?.slice(0, 16) || note.created_at?.slice(0, 16)}
                  </span>
                </div>
                {note.summary && (
                  <p style={{ margin: 0, fontSize: 13, color: 'var(--text-primary)', lineHeight: 1.6 }}>
                    {note.summary}
                  </p>
                )}
                <div
                  style={{
                    marginTop: 'var(--space-xs)',
                    fontSize: 'var(--text-small-size)',
                    color: 'var(--text-tertiary)',
                    cursor: 'pointer',
                    textDecoration: 'underline',
                    textUnderlineOffset: 2,
                  }}
                >
                  点击查看全文 →
                </div>
              </div>
            </GlassCard>
          ))
        )}
      </div>

      <Modal
        open={!!modalNote}
        onCancel={() => setModalNote(null)}
        footer={null}
        width={720}
        styles={{ body: { background: 'var(--bg-primary)', maxHeight: '70vh', overflow: 'auto' } }}
      >
        {modalNote && (
          <div className="markdown-body" style={{ color: 'var(--text-primary)', fontSize: 14, lineHeight: 1.8 }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {modalNote.content}
            </ReactMarkdown>
          </div>
        )}
      </Modal>
    </div>
  );
}
