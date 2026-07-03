import { useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Button, Space, Tour, type TourProps } from 'antd';
import {
  RocketOutlined,
  FilterOutlined,
  ThunderboltOutlined,
  ReadOutlined,
  DollarOutlined,
} from '@ant-design/icons';
import { useOnboardingStore } from '@/stores/onboarding';
import { useSettingsStore } from '@/stores/settings';

interface Step {
  key: string;
  title: string;
  description: string;
  /** Rendered as the "go to" button to send the user to the right page. */
  path?: string;
  icon: React.ReactNode;
}

const STEPS: Step[] = [
  {
    key: 'welcome',
    title: '欢迎来到 AD-RESEARCH',
    description:
      '这是一个面向 A 股、美股、港股、加密货币等市场的量化研究平台。我们会用 5 步带你了解核心功能。',
    icon: <RocketOutlined />,
  },
  {
    key: 'dashboard',
    title: '首页看板',
    description:
      '首页汇总你的综合评分、收藏标的、实时行情与重要新闻。建议每天先看这一页，把握市场全貌。',
    icon: <RocketOutlined />,
  },
  {
    key: 'screen',
    title: '全市场筛选器',
    description:
      '在这里按评分、RSI、夏普、波动率等条件筛选标的。先选条件再点查询，比漫无目的浏览高效得多。',
    path: '/screen',
    icon: <FilterOutlined />,
  },
  {
    key: 'signals',
    title: '交易信号',
    description:
      '信号看板汇总所有策略今日的买入 / 卖出 / 持有建议。点击行可跳到策略说明，回顾触发原因。',
    path: '/signals',
    icon: <ThunderboltOutlined />,
  },
  {
    key: 'research',
    title: 'AI 研究笔记',
    description:
      '把市场观察、宏观数据、技术面结合 LLM 生成可读性强的研报。点击「生成研报」按钮即可触发。',
    path: '/research',
    icon: <ReadOutlined />,
  },
  {
    key: 'paper',
    title: '试着做一笔模拟交易',
    description:
      '模拟交易不涉及真实资金。先创建账户，下一笔小单练手，再开启自动交易看策略表现。',
    path: '/paper-trading',
    icon: <DollarOutlined />,
  },
];

/**
 * OnboardingTour is the global 5-step first-time tour. It mounts in AppLayout
 * and only opens when:
 *   - the user has not completed onboarding (state in localStorage), AND
 *   - the current path is one of the "anchor" pages for the steps
 *      (default: /dashboard).
 *
 * Users can also reopen it from the user-menu entry "重新触发新手引导".
 */
export default function OnboardingTour() {
  const location = useLocation();
  const { completed, reopen, setCompleted, triggerReopen, clearReopen } =
    useOnboardingStore();
  const { mode, setMode } = useSettingsStore();
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState(0);

  // Trigger logic — open when not completed and we're on /dashboard, or when
  // the user explicitly clicks "reopen".
  useEffect(() => {
    if (reopen) {
      setCurrent(0);
      setOpen(true);
      clearReopen();
      return;
    }
    if (completed) return;
    if (location.pathname !== '/dashboard') return;
    setCurrent(0);
    setOpen(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname, completed, reopen]);

  const tourSteps: TourProps['steps'] = useMemo(
    () =>
      STEPS.map((s, idx) => ({
        title: (
          <Space>
            <span className="onboarding-tour__step-icon">{s.icon}</span>
            <span>{`第 ${idx + 1} 步 / 共 ${STEPS.length} 步`}</span>
          </Space>
        ),
        description: (
          <div>
            <div className="onboarding-tour__title">{s.title}</div>
            <div className="onboarding-tour__desc">{s.description}</div>
            {s.path && (
              <Button
                type="link"
                size="small"
                className="onboarding-tour__go"
                onClick={() => {
                  // Mark as completed; user has clearly seen enough.
                  setOpen(false);
                  setCompleted(true);
                  window.location.assign(s.path!);
                }}
              >
                去{s.title}看看 →
              </Button>
            )}
          </div>
        ),
        // We do not bind to a DOM element because each step lives on a
        // different route. The modal-style centered tour handles that well
        // for a 5-step first-time experience.
        target: null,
      })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const handleFinish = () => {
    setOpen(false);
    setCompleted(true);
  };

  return (
    <>
      <Tour
        open={open}
        onClose={() => setOpen(false)}
        onFinish={handleFinish}
        current={current}
        onChange={setCurrent}
        steps={tourSteps}
        indicatorsRender={(currentStep, total) => (
          <span className="onboarding-tour__indicator">
            {currentStep + 1} / {total}
          </span>
        )}
        // Pre-step 0 callout: let users opt-out before the tour starts so it
        // doesn't feel like a wall of modal text.
        // Note: AntD Tour has no built-in pre-confirm, so we attach it as a
        // ghost button inside the description via the first step's content.
      />

      {/* Hidden helper: re-open the tour from the user menu — called via
          window.dispatchEvent('ad-research:reopen-onboarding'). This avoids
          wiring extra props through AppLayout. */}
      <ReopenListener triggerReopen={triggerReopen} />

      {/* Hidden helper: switch mode from any component via custom event. */}
      <ModeListener mode={mode} setMode={setMode} />
    </>
  );
}

/**
 * Listen for a global "reopen onboarding" event so AppLayout can dispatch
 * without prop-drilling the trigger function through the React tree.
 */
function ReopenListener({ triggerReopen }: { triggerReopen: () => void }) {
  useEffect(() => {
    const handler = () => triggerReopen();
    window.addEventListener('ad-research:reopen-onboarding', handler);
    return () => window.removeEventListener('ad-research:reopen-onboarding', handler);
  }, [triggerReopen]);
  return null;
}

function ModeListener({
  mode,
  setMode,
}: {
  mode: 'novice' | 'pro';
  setMode: (m: 'novice' | 'pro') => void;
}) {
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<{ mode: 'novice' | 'pro' }>).detail;
      if (detail?.mode) setMode(detail.mode);
    };
    window.addEventListener('ad-research:set-help-mode', handler);
    return () => window.removeEventListener('ad-research:set-help-mode', handler);
  }, [setMode]);
  // Keep mode in a data attribute for any CSS hooks; harmless.
  useEffect(() => {
    document.documentElement.dataset.helpMode = mode;
  }, [mode]);
  return null;
}