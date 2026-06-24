import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Select, Button, Input, Tag, Skeleton, Modal, Empty } from 'antd';
import { RobotOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { researchApi, ResearchNote } from '@/api/research';
import GlassCard from '@/components/GlassCard';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const SENTIMENT_COLORS: Record<string, string> = {
  bullish: '#22c55e',
  bearish: '#ef4444',
  neutral: '#eab308',
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
      <GlassCard>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <Input
            placeholder="输入标的代码 (如 SPY.US, AAPL.US)"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            onPressEnter={handleGenerate}
            style={{ flex: 1, minWidth: 200 }}
            prefix={<ThunderboltOutlined style={{ color: '#818cf8' }} />}
          />
          <Button
            type="primary"
            icon={<RobotOutlined />}
            loading={generateMutation.isPending}
            onClick={handleGenerate}
            style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)', border: 'none' }}
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

      <div style={{ marginTop: 20 }}>
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
            <GlassCard key={note.id} style={{ marginBottom: 16 }}>
              <div
                style={{ cursor: 'pointer' }}
                onClick={() => setModalNote(note)}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 14, fontWeight: 600, color: '#818cf8', fontFamily: "'SF Mono', monospace" }}>
                      {note.instrument_code}
                    </span>
                    <Tag style={{ margin: 0, borderRadius: 6, fontSize: 11 }}>{note.note_type}</Tag>
                    {note.sentiment && (
                      <span
                        style={{
                          fontSize: 12,
                          fontWeight: 600,
                          color: SENTIMENT_COLORS[note.sentiment] || '#94a3b8',
                          padding: '2px 8px',
                          borderRadius: 6,
                          background: `${SENTIMENT_COLORS[note.sentiment]}15` || 'rgba(255,255,255,0.04)',
                        }}
                      >
                        {SENTIMENT_LABELS[note.sentiment] || note.sentiment}
                      </span>
                    )}
                    {note.confidence && (
                      <span style={{ fontSize: 11, color: '#64748b' }}>
                        置信度 {note.confidence}/10
                      </span>
                    )}
                  </div>
                  <span style={{ fontSize: 11, color: '#475569', whiteSpace: 'nowrap' }}>
                    {note.generated_at?.slice(0, 16) || note.created_at?.slice(0, 16)}
                  </span>
                </div>
                {note.summary && (
                  <p style={{ margin: 0, fontSize: 13, color: '#e2e8f0', lineHeight: 1.6 }}>
                    {note.summary}
                  </p>
                )}
                <div
                  style={{
                    marginTop: 8,
                    fontSize: 12,
                    color: '#64748b',
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
        styles={{ body: { background: '#0f1729', maxHeight: '70vh', overflow: 'auto' } }}
      >
        {modalNote && (
          <div className="markdown-body" style={{ color: '#e2e8f0', fontSize: 14, lineHeight: 1.8 }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {modalNote.content}
            </ReactMarkdown>
          </div>
        )}
      </Modal>
    </div>
  );
}
