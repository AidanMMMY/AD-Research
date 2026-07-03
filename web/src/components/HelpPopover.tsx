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
      signal_dashboard: '交易信号',
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
      <div className="help-popover">
        {/* Header */}
        <div className="help-popover__header">
          <div className="help-popover__icon-wrap">
            <BookOutlined className="help-popover__icon" />
          </div>
          <span className="help-popover__title">{term.title}</span>
        </div>

        {/* Short description / full description */}
        <div className="help-popover__body">{term.fullDesc}</div>

        {/* Formula */}
        {term.formula && (
          <div className="help-popover__formula">
            <div className="help-popover__label">公式</div>
            <div className="help-popover__code">{term.formula}</div>
          </div>
        )}

        {/* Interpretation */}
        {term.interpretation && (
          <div className={`help-popover__section ${term.example ? '' : 'help-popover__section--spaced'}`}>
            <span className="help-popover__caption">解读：</span>
            <span className="help-popover__text">{term.interpretation}</span>
          </div>
        )}

        {/* Example */}
        {term.example && (
          <div className="help-popover__section help-popover__section--spaced">
            <span className="help-popover__caption">案例：</span>
            <span className="help-popover__text">{term.example}</span>
          </div>
        )}

        {/* Divider */}
        <div className="help-popover__divider" />

        {/* Footer action */}
        <div className="help-popover__footer">
          <Button
            type="primary"
            size="small"
            icon={<RobotOutlined />}
            onClick={() =>
              handleAskAI(term.title, term.shortDesc, term.relatedPageType, contextData)
            }
            className="help-popover__ask-btn"
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
        className="help-popover__trigger"
        style={style}
      >
        {children || term.title}
        <InfoCircleOutlined
          className="help-popover__info-icon"
        />
      </span>
    </Popover>
  );
}
