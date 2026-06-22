import { getReturnColor, getReturnBgColor, getReturnBorderColor } from '@/utils/color';
import { formatPercent } from '@/utils/format';

interface ReturnTagProps {
  value?: number | null;
}

export default function ReturnTag({ value }: ReturnTagProps) {
  if (value === undefined || value === null) {
    return (
      <span
        style={{
          display: 'inline-block',
          padding: '3px 10px',
          borderRadius: 6,
          fontSize: 12,
          fontWeight: 600,
          fontFamily: "'SF Mono', 'Fira Code', monospace",
          color: '#64748b',
          background: 'rgba(255,255,255,0.03)',
          border: '1px solid rgba(255,255,255,0.06)',
        }}
      >
        -
      </span>
    );
  }
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '3px 10px',
        borderRadius: 6,
        fontSize: 12,
        fontWeight: 600,
        fontFamily: "'SF Mono', 'Fira Code', monospace",
        color: getReturnColor(value),
        background: getReturnBgColor(value),
        border: `1px solid ${getReturnBorderColor(value)}`,
        transition: 'all 150ms ease',
      }}
    >
      {formatPercent(value)}
    </span>
  );
}
