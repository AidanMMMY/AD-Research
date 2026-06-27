import { useMemo } from 'react';
import { Popover, Button, Space, Divider } from 'antd';
import { InfoCircleOutlined, RobotOutlined, BookOutlined } from '@ant-design/icons';
import { getTerm } from '@/utils/termDictionary';
import { useAIHelp } from '@/hooks/useAIHelp';
import type { HelpContext } from '@/types/help';

interface HelpPopoverProps {
  /** 术语 key */
  termKey: string;
  /** 自定义显示文本，默认使用词典中的 title */
  children?: React.ReactNode;
  /** 额外上下文，点击“问 AI”时会拼接进问题 */
  contextData?: string;
  /** 触发方式，默认 hover */
  trigger?: 'hover' | 'click';
  /** 自定义样式 */
  style?: React.CSSProperties;
  /** 是否启用，默认 true */
  enabled?: boolean;
}

export default function HelpPopover({
  termKey,
  children,
  contextData = '',
  trigger = 'hover',
  style,
  enabled = true,
}: HelpPopoverProps) {
  const { open } = useAIHelp();
  const term = getTerm(termKey);

  const content = useMemo(() => {
    if (!term) return null;

    return (
      <div style={{ maxWidth: 320 }}>
        <div
          style={{
            fontSize: 15,
            fontWeight: 600,
            color: '#f1f5f9',
            marginBottom: 8,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <BookOutlined style={{ color: '#818cf8' }} />
          {term.title}
        </div>

        <div style={{ fontSize: 13, color: '#e2e8f0', lineHeight: 1.7, marginBottom: 10 }}>
          {term.fullDesc}
        </div>

        {term.formula && (
          <div
            style={{
              background: 'rgba(255,255,255,0.05)',
              border: '1px solid rgba(255,255,255,0.08)',
              borderRadius: 8,
              padding: '8px 12px',
              marginBottom: 10,
              fontSize: 13,
              color: '#a5b4fc',
              fontFamily: "'SF Mono', 'Fira Code', monospace",
            }}
          >
            {term.formula}
          </div>
        )}

        {term.interpretation && (
          <div style={{ fontSize: 12, color: '#94a3b8', lineHeight: 1.6, marginBottom: 8 }}>
            <strong style={{ color: '#e2e8f0' }}>解读：</strong> {term.interpretation}
          </div>
        )}

        {term.example && (
          <div style={{ fontSize: 12, color: '#94a3b8', lineHeight: 1.6, marginBottom: 12 }}>
            <strong style={{ color: '#e2e8f0' }}>案例：</strong> {term.example}
          </div>
        )}

        <Divider style={{ margin: '12px 0', borderColor: 'rgba(255,255,255,0.08)' }} />

        <Space size={8}>
          <Button
            type="primary"
            size="small"
            icon={<RobotOutlined />}
            onClick={() => handleAskAI(term.title, term.shortDesc, term.relatedPageType, contextData)}
            style={{
              background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
              border: 'none',
            }}
          >
            问 AI
          </Button>
        </Space>
      </div>
    );
  }, [term, contextData]);

  const handleAskAI = (
    title: string,
    shortDesc: string,
    relatedPageType: HelpContext['pageType'] | undefined,
    ctx: string
  ) => {
    const pageType = relatedPageType || 'etf_detail';
    const pageTitleMap: Record<HelpContext['pageType'], string> = {
      score_ranking: '评分排名',
      etf_detail: 'ETF 详情',
      strategy_list: '策略管理',
      backtest_detail: '回测详情',
      screen: '全市场筛选器',
      pool_detail: '标的池详情',
    };

    const question = `请详细解释“${title}”这个概念。${shortDesc}`;
    const fullContext = ctx ? `当前页面上下文：\n${ctx}\n\n用户想了解的术语：${title}` : `用户想了解的术语：${title}`;

    open({
      pageType,
      pageTitle: pageTitleMap[pageType],
      contextData: fullContext,
      initialQuestion: question,
      quickQuestions: [
        `“${title}”数值高低代表什么？`,
        `如何用这个指标做投资决策？`,
        `这个指标有什么局限性？`,
      ],
    });
  };

  if (!enabled || !term) {
    return <span style={style}>{children}</span>;
  }

  return (
    <Popover
      content={content}
      trigger={trigger}
      placement="top"
      overlayStyle={{ width: 'auto', maxWidth: 360 }}
      styles={{
        body: {
          background: 'rgba(10, 15, 30, 0.95)',
          border: '1px solid rgba(255,255,255,0.08)',
          borderRadius: 12,
          padding: 16,
          backdropFilter: 'blur(12px)',
        },
      }}
    >
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 4,
          cursor: 'help',
          color: 'inherit',
          ...style,
        }}
      >
        {children || term.title}
        <InfoCircleOutlined
          style={{
            fontSize: 12,
            color: '#64748b',
            opacity: 0.7,
            transition: 'opacity 200ms',
          }}
          className="help-popover-icon"
        />
      </span>
    </Popover>
  );
}
