import { useMemo } from 'react';
import { Popover, Button } from 'antd';
import { InfoCircleOutlined, RobotOutlined, BookOutlined, PartitionOutlined } from '@ant-design/icons';
import { getTerm } from '@/utils/termDictionary';
import { useAIHelp } from '@/hooks/useAIHelp';
import { useIsMobile } from '@/hooks/useBreakpoint';
import { useSettingsStore } from '@/stores/settings';
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
  /**
   * K14: 教学模式覆盖。默认从 useSettingsStore 读取。
   *   - novice: 显示更长 fullDesc + example + interpretation
   *   - pro:    仅显示 fullDesc
   */
  mode?: 'novice' | 'pro';
}

export default function HelpPopover({
  termKey,
  children,
  contextData = '',
  trigger,
  style,
  enabled = true,
  mode: modeOverride,
}: HelpPopoverProps) {
  const { open } = useAIHelp();
  const isMobile = useIsMobile();
  const settingsMode = useSettingsStore((s) => s.mode);
  const mode = modeOverride ?? settingsMode;
  const term = getTerm(termKey);
  const effectiveTrigger = trigger ?? (isMobile ? 'click' : 'hover');

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
      // M22-1 (2026-07-04): added for type completeness after the
      // Global Markets page started sending ``pageType='global_markets'``
      // to the AI Help drawer. The popover never renders this label
      // because no term has ``relatedPageType='global_markets'``; the
      // entry only exists so the ``Record<HelpPageType, string>``
      // exhaustiveness check passes.
      global_markets: '全球市场速览',
    };

    // K14: novice 模式下给 AI 教学助手额外的「为什么需要看」上下文
    const novicePrefix =
      mode === 'novice'
        ? '我是一个新手，请先简单解释这个概念的现实意义，再给一个具体例子。'
        : '';
    const question = `${novicePrefix}请详细解释"${title}"这个概念。${shortDesc}`.trim();
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

    // K14: novice 模式展示三段（why / what / how），pro 模式只展示一段。
    const showNovice = mode === 'novice';

    return (
      <div className="help-popover">
        {/* Header */}
        <div className="help-popover__header">
          <div className="help-popover__icon-wrap">
            <BookOutlined className="help-popover__icon" />
          </div>
          <span className="help-popover__title">{term.title}</span>
          {showNovice && (
            <span className="help-popover__mode-badge">新手模式</span>
          )}
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

        {/* Example — novice 模式下突出 */}
        {term.example && (
          <div className="help-popover__section help-popover__section--spaced">
            <span className="help-popover__caption">{showNovice ? '举个例子：' : '案例：'}</span>
            <span className="help-popover__text">{term.example}</span>
          </div>
        )}

        {/* Divider */}
        <div className="help-popover__divider" />

        {/* M20: 相关术语 chip 链接 — 只展示，点击仅 console.log；P2 再接跳词条详情 */}
        {term.relatedTerms && term.relatedTerms.length > 0 && (
          <div className="help-popover__related">
            <span className="help-popover__related-label">
              <PartitionOutlined /> 相关术语
            </span>
            <div className="help-popover__related-chips">
              {term.relatedTerms.map((rk) => {
                const rt = getTerm(rk);
                if (!rt) return null;
                return (
                  <span
                    key={rk}
                    role="button"
                    tabIndex={0}
                    className="help-popover__related-chip"
                    onClick={(e) => {
                      e.stopPropagation();
                      // TODO(M20-P2): 接入词条详情页跳转。当前仅 console 占位。
                      console.log('[M20] related-term clicked', { from: termKey, to: rk });
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        console.log('[M20] related-term activated', { from: termKey, to: rk });
                      }
                    }}
                    title={`${rt.title} — ${rt.shortDesc}`}
                  >
                    {rt.title}
                  </span>
                );
              })}
            </div>
          </div>
        )}

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
            {showNovice ? '让 AI 再讲明白一点' : '问 AI'}
          </Button>
        </div>
      </div>
    );
  }, [term, contextData, mode]);

  if (!enabled || !term) {
    return <span style={style}>{children}</span>;
  }

  return (
    <Popover
      content={content}
      trigger={effectiveTrigger}
      placement="top"
      overlayStyle={{ width: 'auto', maxWidth: 'min(380px, 90vw)' }}
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