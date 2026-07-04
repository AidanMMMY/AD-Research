import { getScoreColor } from '@/utils/color';

interface ScoreBarProps {
  score: number;
  size?: 'small' | 'default';
}

export default function ScoreBar({ score, size = 'default' }: ScoreBarProps) {
  return (
    <div className="score-bar">
      <div
        className={`score-bar__track score-bar__track--${size}`}
      >
        <div
          className="score-bar__fill"
          style={{
            // data-driven: fill width and color depend on the score prop
            width: `${Math.min(score, 100)}%`,
            background: getScoreColor(score),
          }}
        />
      </div>
      {size !== 'small' && (
        <span
          className="score-bar__value tabular-nums"
          style={{
            // data-driven: value color depends on the score prop
            color: getScoreColor(score),
          }}
        >
          {score.toFixed(1)}
        </span>
      )}
    </div>
  );
}
