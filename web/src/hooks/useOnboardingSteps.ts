import { useMemo, createElement } from 'react';
import {
  RocketOutlined,
  FilterOutlined,
  ThunderboltOutlined,
  ReadOutlined,
  DollarOutlined,
} from '@ant-design/icons';

export interface OnboardingStep {
  key: string;
  title: string;
  description: string;
  /** Rendered as the "go to" button to send the user to the right page. */
  path?: string;
  icon: React.ReactNode;
  /**
   * Selector for the DOM element the tour step should anchor to.
   * If the element is not present, the tour falls back to a centered modal.
   */
  target: () => HTMLElement | null;
}

const querySelector = (selector: string): (() => HTMLElement | null) => {
  return () => (typeof document === 'undefined' ? null : document.querySelector<HTMLElement>(selector));
};

const icon = (node: React.ReactNode) => node;

/**
 * Returns the ordered list of onboarding tour steps. Each step may bind to
 * a real DOM element via `target()`; the Tour component will fall back to a
 * centered modal when no target is found.
 *
 * Step→page mapping (kept loose so the user can navigate freely):
 *   - welcome        : any page with PageHeader (defaults to /dashboard)
 *   - dashboard      : /dashboard
 *   - filter-toolbar : /screen
 *   - signals-panel  : /signals
 *   - research-notes : /research
 *   - paper-account  : /paper-trading
 */
export function useOnboardingSteps(): OnboardingStep[] {
  return useMemo<OnboardingStep[]>(
    () => [
      {
        key: 'welcome',
        title: '欢迎来到 AD-RESEARCH',
        description:
          '这是一个面向 A 股、美股、港股、加密货币等市场的量化研究平台。我们会用 5 步带你了解核心功能。',
        icon: createElement(RocketOutlined),
        // Default anchor: Dashboard's PageHeader. Falls back to centered modal
        // if user lands on a non-dashboard page first.
        target: querySelector('[data-onboard="welcome-dashboard"]'),
      },
      {
        key: 'dashboard',
        title: '首页看板',
        description:
          '首页汇总你的综合评分、收藏标的、实时行情与重要新闻。建议每天先看这一页，把握市场全貌。',
        icon: createElement(RocketOutlined),
        target: querySelector('[data-onboard="welcome-dashboard"]'),
      },
      {
        key: 'screen',
        title: '全市场筛选器',
        description:
          '在这里按评分、RSI、夏普、波动率等条件筛选标的。先选条件再点查询，比漫无目的浏览高效得多。',
        path: '/screen',
        icon: createElement(FilterOutlined),
        target: querySelector('[data-onboard="filter-toolbar"]'),
      },
      {
        key: 'signals',
        title: '交易信号',
        description:
          '信号看板汇总所有策略今日的买入 / 卖出 / 持有建议。点击行可跳到策略说明，回顾触发原因。',
        path: '/signals',
        icon: createElement(ThunderboltOutlined),
        target: querySelector('[data-onboard="signals-panel"]'),
      },
      {
        key: 'research',
        title: 'AI 研究笔记',
        description:
          '把市场观察、宏观数据、技术面结合 LLM 生成可读性强的研报。点击「生成研报」按钮即可触发。',
        path: '/research',
        icon: createElement(ReadOutlined),
        target: querySelector('[data-onboard="research-notes"]'),
      },
      {
        key: 'paper',
        title: '试着做一笔模拟交易',
        description:
          '模拟交易不涉及真实资金。先创建账户，下一笔小单练手，再开启自动交易看策略表现。',
        path: '/paper-trading',
        icon: createElement(DollarOutlined),
        target: querySelector('[data-onboard="paper-account"]'),
      },
    ],
    []
  );
}

// Silence "unused" warning in case tree-shaking prunes icon()
void icon;