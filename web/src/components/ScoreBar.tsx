import { getScoreColor } from '@/utils/color';

interface ScoreBarProps {
  score: number;
  size?: 'small' | 'default';
}

export default function ScoreBar({ score, size = 'default' }: ScoreBarProps) {
  const height = size === 'small' ? 4 : 6;
  return (
    <div className="score-bar">
      <div
        className="score-bar__track"
        style={{ height, borderRadius: height / 2 }}
      >
        <div
          className="score-bar__fill"
          style={{
            width: `${Math.min(score, 100)}%`,
            background: getScoreColor(score),
            borderRadius: height / 2,
          }}
        />
      </div>
      {size !== 'small' && (
        <span
          className="score-bar__value tabular-nums"
          style={{ color: getScoreColor(score) }}
        >
          {score.toFixed(1)}
        </span>
      )}
    </div>
  );
}
