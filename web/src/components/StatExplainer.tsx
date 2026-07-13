import { useMemo } from 'react';
import { Popover } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';
import { getTerm } from '@/utils/termDictionary';
import { useSettingsStore } from '@/stores/settings';

interface StatExplainerProps {
  /** termDictionary 中的 key；找不到则不渲染 */
  termKey?: string;
  /** 自定义一句话说明；优先级高于 term.shortDesc */
  text?: string;
  /** 自定义展开内容；优先级高于 term.fullDesc */
  expanded?: string;
  /** 触发方式（默认 hover） */
  trigger?: 'hover' | 'click';
  /** 是否禁用：当 settings.learningMode 为关时强制不渲染 */
  respectLearningMode?: boolean;
  className?: string;
}

/**
 * K15: 学习模式下的"一句话解释"。挂在 StatCard 下方，hover/click 展开。
 * 设计原则：
 *  - 必须自己读 useSettingsStore.learningMode，避免每个父组件都传 props
 *  - 找不到 term 时静默不渲染，绝不可崩
 *  - 不影响原 StatCard 布局（一行 ≤ 36px 的小字）
 */
export default function StatExplainer({
  termKey,
  text,
  expanded,
  trigger = 'hover',
  respectLearningMode = true,
  className,
}: StatExplainerProps) {
  const learningMode = useSettingsStore((s) => s.learningMode);

  const term = useMemo(() => (termKey ? getTerm(termKey) : undefined), [termKey]);
  const summary = text ?? term?.shortDesc;
  const detail = expanded ?? term?.fullDesc;

  if (respectLearningMode && !learningMode) return null;
  if (!summary) return null;

  if (!detail) {
    // No detailed content to expand — render as a static one-liner.
    return (
      <div
        className={`stat-explainer ${className || ''}`}
        aria-label="stat-explainer-static"
      >
        {summary}
      </div>
    );
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    // Activate on Space/Enter so keyboard users reach the popover without
    // needing a pointer device. AntD Popover's `click` trigger already does
    // this for mouse, but the `hover` default leaves keyboard users stranded.
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      e.currentTarget.click();
    }
  };

  return (
    <Popover
      content={<div className="stat-explainer__popover">{detail}</div>}
      trigger={trigger}
      placement="top"
      overlayStyle={{ maxWidth: 'min(320px, 88vw)' }}
    >
      <div
        className={`stat-explainer stat-explainer--clickable ${className || ''}`}
        role="button"
        tabIndex={0}
        aria-label="stat-explainer"
        onKeyDown={handleKeyDown}
      >
        <InfoCircleOutlined className="stat-explainer__icon" />
        <span className="stat-explainer__text">{summary}</span>
      </div>
    </Popover>
  );
}
