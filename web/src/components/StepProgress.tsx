import { CheckOutlined, LoadingOutlined, CloseCircleOutlined, ClockCircleOutlined } from '@ant-design/icons';
import type { Step } from '@/hooks/useStepStream';

interface StepProgressProps {
  steps: Step[];
  compact?: boolean;
}

const STATUS_ICONS: Record<Step['status'], React.ReactNode> = {
  pending: <ClockCircleOutlined style={{ color: 'var(--text-tertiary)' }} />,
  running: <LoadingOutlined style={{ color: 'var(--accent)' }} />,
  done: <CheckOutlined style={{ color: 'var(--color-success-bright)' }} />,
  error: <CloseCircleOutlined style={{ color: 'var(--color-error-bright)' }} />,
};

export default function StepProgress({ steps, compact = false }: StepProgressProps) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: compact ? 4 : 6,
        padding: compact ? '6px 0' : '8px 0',
        fontSize: compact ? 12 : 13,
        color: 'var(--text-secondary)',
      }}
    >
      {steps.map((s) => {
        const dim = s.status === 'pending';
        return (
          <div
            key={s.id}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              opacity: dim ? 0.55 : 1,
              transition: 'opacity 200ms',
            }}
          >
            <span style={{ display: 'inline-flex', alignItems: 'center', fontSize: compact ? 12 : 14 }}>
              {STATUS_ICONS[s.status]}
            </span>
            <span style={{ color: s.status === 'running' ? 'var(--text-primary)' : 'var(--text-secondary)' }}>
              {s.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}