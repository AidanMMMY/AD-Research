import { CheckOutlined, LoadingOutlined, CloseCircleOutlined, ClockCircleOutlined } from '@ant-design/icons';
import type { Step } from '@/hooks/useStepStream';

interface StepProgressProps {
  steps: Step[];
  compact?: boolean;
}

const STATUS_ICONS: Record<Step['status'], React.ReactNode> = {
  pending: <ClockCircleOutlined />,
  running: <LoadingOutlined />,
  done: <CheckOutlined />,
  error: <CloseCircleOutlined />,
};

export default function StepProgress({ steps, compact = false }: StepProgressProps) {
  return (
    <div
      className={`step-progress ${compact ? 'step-progress--compact' : 'step-progress--default'}`}
    >
      {steps.map((s) => {
        const dim = s.status === 'pending';
        return (
          <div
            key={s.id}
            className={`step-progress__row ${dim ? 'step-progress__row--dim' : ''}`}
          >
            <span className={`step-progress__icon step-progress__icon--${s.status} ${compact ? 'step-progress__icon--compact' : 'step-progress__icon--default'}`}>
              {STATUS_ICONS[s.status]}
            </span>
            <span className={`step-progress__label ${s.status === 'running' ? 'step-progress__label--running' : ''}`}>
              {s.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
