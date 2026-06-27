import { getScoreColor, getScoreGradient } from '@/utils/color';

interface ScoreBarProps {
  score: number;
  size?: 'small' | 'default';
}

export default function ScoreBar({ score, size = 'default' }: ScoreBarProps) {
  const height = size === 'small' ? 4 : 6;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%' }}>
      <div
        style={{
          flex: 1,
          height,
          background: 'var(--bg-input)',
          borderRadius: height / 2,
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        <div
          style={{
            width: `${Math.min(score, 100)}%`,
            height: '100%',
            background: getScoreGradient(score),
            borderRadius: height / 2,
            transition: 'width 600ms cubic-bezier(0.4, 0, 0.2, 1)',
          }}
        />
      </div>
      {size !== 'small' && (
        <span
          style={{
            fontSize: 'var(--text-body)',
            fontWeight: 500,
            color: getScoreColor(score),
            fontFamily: 'var(--font-mono)',
            minWidth: 40,
            textAlign: 'right',
          }}
        >
          {score.toFixed(1)}
        </span>
      )}
    </div>
  );
}
