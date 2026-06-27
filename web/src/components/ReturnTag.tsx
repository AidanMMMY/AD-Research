import type { CSSProperties } from 'react';
import { getReturnColor, getReturnBgColor, getReturnBorderColor } from '@/utils/color';
import { formatPercent } from '@/utils/format';
import { useSettingsStore } from '@/stores/settings';

interface ReturnTagProps {
  value?: number | null;
}

const baseStyle: CSSProperties = {
  display: 'inline-block',
  padding: '2px 8px',
  borderRadius: 'var(--radius-sm)',
  fontSize: 'var(--text-code-size)',
  fontWeight: 500,
  fontFamily: 'var(--font-mono)',
  transition: 'all var(--transition-fast)',
};

export default function ReturnTag({ value }: ReturnTagProps) {
  const colorConvention = useSettingsStore((s) => s.colorConvention);

  if (value === undefined || value === null) {
    return (
      <span
        style={{
          ...baseStyle,
          color: 'var(--text-tertiary)',
          background: 'var(--bg-input)',
          border: '1px solid var(--border-default)',
        }}
      >
        -
      </span>
    );
  }
  return (
    <span
      style={{
        ...baseStyle,
        color: getReturnColor(value, colorConvention),
        background: getReturnBgColor(value, colorConvention),
        border: `1px solid ${getReturnBorderColor(value, colorConvention)}`,
      }}
    >
      {formatPercent(value)}
    </span>
  );
}
