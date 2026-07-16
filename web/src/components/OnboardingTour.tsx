import { useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Button, Space, Tour, type TourProps } from 'antd';
import { useOnboardingStore } from '@/stores/onboarding';
import { useSettingsStore } from '@/stores/settings';
import { useOnboardingSteps } from '@/hooks/useOnboardingSteps';
import { useFocusRestore } from '@/hooks/useFocusRestore';

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
  const STEPS = useOnboardingSteps();

  // WCAG 2.4.3: when the onboarding tour closes (either via Skip or via
  // Finish), return keyboard focus to the element that triggered the
  // tour (typically the dashboard root, or the user-menu entry that
  // called "重新触发新手引导").
  useFocusRestore(open);

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

  const handleSkip = () => {
    // WCAG 2.2.1 (Timing Adjustable) / 2.4.3 (Focus Order): users can bail
    // out of the tour at any time. We mark completed so it never auto-pops
    // again and close the surface so useFocusRestore returns keyboard
    // focus to the trigger.
    setOpen(false);
    setCompleted(true);
  };

  const tourSteps: TourProps['steps'] = useMemo(
    () =>
      STEPS.map((s, idx) => ({
        title: (
          <Space style={{ width: '100%', justifyContent: 'space-between' }}>
            <Space>
              <span className="onboarding-tour__step-icon">{s.icon}</span>
              <span>{`第 ${idx + 1} 步 / 共 ${STEPS.length} 步`}</span>
            </Space>
            {/* WCAG 2.4.1 (Bypass Blocks): "Skip Tour" link gives users a
                one-click exit at every step, not just the last. Visually
                unobtrusive (link, not button) so it doesn't compete with
                the primary "Next / Finish" CTA. */}
            <Button
              type="link"
              size="small"
              className="onboarding-tour__skip"
              onClick={handleSkip}
            >
              跳过引导
            </Button>
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
        // Anchor to a real DOM element when available (M19 P1). Falls back to
        // a centered modal when the target selector returns null (e.g. user
        // is on the wrong page for the current step).
        target: s.target?.() ?? null,
      })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [STEPS]
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