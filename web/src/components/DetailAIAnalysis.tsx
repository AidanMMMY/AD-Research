import { useNavigate } from 'react-router-dom';
import { Row, Col, Button, Skeleton } from 'antd';
import { RobotOutlined, ReadOutlined, SmileOutlined } from '@ant-design/icons';
import Panel from '@/components/Panel';
import HelpPopover from '@/components/HelpPopover';
import ThemeTag from '@/components/ThemeTag';
import { useSettingsStore } from '@/stores/settings';
import { SENTIMENT_COLORS, SENTIMENT_LABELS } from '@/utils/sentiment';
import type { ResearchNote } from '@/api/research';

interface DetailAIAnalysisProps {
  code: string;
  latestNote: ResearchNote | undefined;
  sentiment: any;
  notesLoading: boolean;
  sentimentLoading: boolean;
  isGenerating: boolean;
  onGenerate: () => void;
}

export default function DetailAIAnalysis({
  code,
  latestNote,
  sentiment,
  notesLoading,
  sentimentLoading,
  isGenerating,
  onGenerate,
}: DetailAIAnalysisProps) {
  const navigate = useNavigate();
  const mode = useSettingsStore((s) => s.mode);

  return (
    <div className="detail-tab-panel">
      {notesLoading || sentimentLoading ? (
        <Panel title="AI分析" padding="md">
          <Skeleton active paragraph={{ rows: 8 }} />
        </Panel>
      ) : (
        <Row gutter={[16, 16]}>
          <Col xs={24} md={12}>
            <Panel
              variant="default"
              className="ai-analysis-panel"
              title={
                <span>
                  <ReadOutlined className="detail-tab-icon detail-tab-icon--lg" />
                  <HelpPopover termKey="ai_research_note" mode={mode}>AI 研究笔记</HelpPopover>
                </span>
              }
              extra={
                <Button
                  size="small"
                  type="primary"
                  icon={<RobotOutlined />}
                  loading={isGenerating}
                  disabled={isGenerating}
                  onClick={onGenerate}
                >
                  生成研报
                </Button>
              }
              padding="md"
            >
              {latestNote ? (
                <div>
                  <div className="ai-note-meta">
                    {latestNote.sentiment && (
                      <ThemeTag
                        variant={
                          latestNote.sentiment === 'bullish' || latestNote.sentiment === 'positive'
                            ? 'rise'
                            : latestNote.sentiment === 'bearish' || latestNote.sentiment === 'negative'
                              ? 'fall'
                              : 'neutral'
                        }
                      >
                        {SENTIMENT_LABELS[latestNote.sentiment] || latestNote.sentiment}
                      </ThemeTag>
                    )}
                    {latestNote.confidence && (
                      <span className="ai-note-confidence">
                        置信度 {latestNote.confidence}/10
                      </span>
                    )}
                    <span className="ai-note-time">
                      {latestNote.generated_at?.slice(0, 16) || latestNote.created_at?.slice(0, 16)}
                    </span>
                  </div>
                  <p className="ai-note-summary">{latestNote.summary}</p>
                  <Button
                    type="link"
                    size="small"
                    onClick={() => navigate('/research')}
                    className="detail-link-button"
                  >
                    查看全部研报 →
                  </Button>
                </div>
              ) : (
                <div className="ai-empty">
                  <RobotOutlined className="ai-empty__icon" />
                  <p>暂无AI研报</p>
                  <p className="ai-empty__hint">点击上方"生成研报"按钮开始分析</p>
                </div>
              )}
            </Panel>
          </Col>

          <Col xs={24} md={12}>
            <Panel
              variant="default"
              className="ai-analysis-panel"
              title={
                <span>
                  <SmileOutlined className="detail-tab-icon detail-tab-icon--lg" />
                  <HelpPopover termKey="market_sentiment" mode={mode}>市场情绪</HelpPopover>
                </span>
              }
              padding="md"
            >
              {sentiment ? (
                <div className="ai-empty">
                  <div
                    className="sentiment-score"
                    style={{ color: SENTIMENT_COLORS[sentiment.label] || 'var(--text-secondary)' }}
                  >
                    {sentiment.avg_score?.toFixed(2) ?? '—'}
                  </div>
                  <ThemeTag
                    variant={
                      sentiment.label === 'bullish' || sentiment.label === 'positive'
                        ? 'rise'
                        : sentiment.label === 'bearish' || sentiment.label === 'negative'
                          ? 'fall'
                          : 'neutral'
                    }
                    className="sentiment-tag"
                  >
                    {SENTIMENT_LABELS[sentiment.label] || sentiment.label}
                  </ThemeTag>

                  <div className="sentiment-bar">
                    <div
                      className="sentiment-bar__fill"
                      style={{
                        width: `${((sentiment.avg_score + 1) / 2) * 100}%`,
                        background: SENTIMENT_COLORS[sentiment.label] || 'var(--text-secondary)',
                      }}
                    />
                  </div>

                  <div className="sentiment-counts">
                    <span className="sentiment-counts__item sentiment-counts__item--positive tabular-nums">正面 {sentiment.positive_count}</span>
                    <span className="sentiment-counts__item sentiment-counts__item--neutral tabular-nums">中性 {sentiment.neutral_count}</span>
                    <span className="sentiment-counts__item sentiment-counts__item--negative tabular-nums">负面 {sentiment.negative_count}</span>
                  </div>
                  <div className="sentiment-meta">
                    共 {sentiment.total_articles} 篇 · 近 {sentiment.period_days} 天
                  </div>
                </div>
              ) : (
                <div className="ai-empty">
                  <SmileOutlined className="ai-empty__icon" />
                  <p>暂无情绪数据</p>
                  <p className="ai-empty__hint">访问情绪仪表盘页面采集数据</p>
                </div>
              )}
            </Panel>
          </Col>
        </Row>
      )}

      <Panel variant="default" className="ai-assistant-cta" padding="md">
        <RobotOutlined className="ai-assistant-cta__icon" />
        <span className="ai-assistant-cta__text">想问AI关于 {code} 的分析？</span>
        <Button
          type="primary"
          icon={<RobotOutlined />}
          onClick={() => navigate(`/chat?symbol=${encodeURIComponent(code || '')}`)}
        >
          打开AI助手
        </Button>
      </Panel>
    </div>
  );
}
