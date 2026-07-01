import { useMemo } from 'react';
import { Popover, Button } from 'antd';
import { InfoCircleOutlined, RobotOutlined, BookOutlined } from '@ant-design/icons';
import { getTerm } from '@/utils/termDictionary';
import { useAIHelp } from '@/hooks/useAIHelp';
import type { HelpContext } from '@/types/help';

interface HelpPopoverProps {
  /** 术语 key */
  termKey: string;
  /** 自定义显示文本，默认使用词典中的 title */
  children?: React.ReactNode;
  /** 额外上下文，点击"问 AI"时会拼接进问题 */
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

  const handleAskAI = (
    title: string,
    shortDesc: string,
    relatedPageType: HelpContext['pageType'] | undefined,
    ctx: string
  ) => {
    const pageType = relatedPageType || 'instrument_detail';
    const pageTitleMap: Record<HelpContext['pageType'], string> = {
      score_ranking: '评分排名',
      instrument_detail: '标的详情',
      strategy_list: '策略管理',
      backtest_detail: '回测详情',
      screen: '全市场筛选器',
      pool_detail: '标的池详情',
      listing_preview: '上市预告',
    };

    const question = `请详细解释"${title}"这个概念。${shortDesc}`;
    const fullContext = ctx
      ? `当前页面上下文：\n${ctx}\n\n用户想了解的术语：${title}`
      : `用户想了解的术语：${title}`;

    open({
      pageType,
      pageTitle: pageTitleMap[pageType],
      contextData: fullContext,
      initialQuestion: question,
      quickQuestions: [
        `"${title}"数值高低代表什么？`,
        `如何用这个指标做投资决策？`,
        `这个指标有什么局限性？`,
      ],
    });
  };

  const content = useMemo(() => {
    if (!term) return null;

    return (
      <div
        style={{
          maxWidth: 340,
          padding: 20,
          color: 'var(--text-primary)',
        }}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-3)',
            marginBottom: 12,
          }}
        >
          <div
            style={{
              width: 28,
              height: 28,
              borderRadius: 8,
              background: 'var(--accent-dim)',
              border: '1px solid var(--accent-border)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <BookOutlined style={{ color: 'var(--accent)', fontSize: 14 }} />
          </div>
          <span
            style={{
              fontSize: 15,
              fontWeight: 600,
              color: 'var(--text-primary)',
              lineHeight: 1.3,
            }}
          >
            {term.title}
          </span>
        </div>

        {/* Short description / full description */}
        <div
          style={{
            fontSize: 13,
            color: 'var(--text-secondary)',
            lineHeight: 1.7,
            marginBottom: 14,
          }}
        >
          {term.fullDesc}
        </div>

        {/* Formula */}
        {term.formula && (
          <div
            style={{
              background: 'var(--bg-input)',
              border: '1px solid var(--border-default)',
              borderLeft: '3px solid var(--accent)',
              borderRadius: '0 8px 8px 0',
              padding: 'var(--space-3) var(--space-3)',
              marginBottom: 14,
            }}
          >
            <div
              style={{
                fontSize: 10,
                fontWeight: 500,
                color: 'var(--text-tertiary)',
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                marginBottom: 6,
              }}
            >
              公式
            </div>
            <div
              style={{
                fontSize: 13,
                color: 'var(--accent)',
                fontFamily: "'SF Mono', 'Fira Code', 'Cascadia Code', monospace",
                lineHeight: 1.5,
                wordBreak: 'break-word',
              }}
            >
              {term.formula}
            </div>
          </div>
        )}

        {/* Interpretation */}
        {term.interpretation && (
          <div
            style={{
              marginBottom: term.example ? 10 : 16,
            }}
          >
            <span
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: 'var(--accent)',
                marginRight: 6,
              }}
            >
              解读：
            </span>
            <span
              style={{
                fontSize: 12,
                color: 'var(--text-secondary)',
                lineHeight: 1.7,
              }}
            >
              {term.interpretation}
            </span>
          </div>
        )}

        {/* Example */}
        {term.example && (
          <div style={{ marginBottom: 16 }}>
            <span
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: 'var(--accent)',
                marginRight: 6,
              }}
            >
              案例：
            </span>
            <span
              style={{
                fontSize: 12,
                color: 'var(--text-secondary)',
                lineHeight: 1.7,
              }}
            >
              {term.example}
            </span>
          </div>
        )}

        {/* Divider */}
        <div
          style={{
            height: 1,
            background: 'var(--border-default)',
            margin: '16px 0',
          }}
        />

        {/* Footer action */}
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Button
            type="primary"
            size="small"
            icon={<RobotOutlined />}
            onClick={() =>
              handleAskAI(term.title, term.shortDesc, term.relatedPageType, contextData)
            }
            style={{
              background: 'var(--accent)',
              border: 'none',
              color: 'var(--text-on-accent)',
              borderRadius: 8,
              fontWeight: 500,
              height: 32,
              padding: '0 14px',
            }}
          >
            问 AI
          </Button>
        </div>
      </div>
    );
  }, [term, contextData]);

  if (!enabled || !term) {
    return <span style={style}>{children}</span>;
  }

  return (
    <Popover
      content={content}
      trigger={trigger}
      placement="top"
      overlayStyle={{ width: 'auto', maxWidth: 380 }}
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
            color: 'var(--text-tertiary)',
            opacity: 0.7,
            transition: 'opacity 200ms',
          }}
          className="help-popover-icon"
        />
      </span>
    </Popover>
  );
}
