import { getReturnColor, getReturnBgColor, getReturnBorderColor } from '@/utils/color';
import { formatPercent } from '@/utils/format';
import { useSettingsStore } from '@/stores/settings';
import React from 'react';

interface ReturnTagProps {
  value?: number | null;
}

const baseStyle = {
  display: 'inline-block',
  padding: '2px 8px',
  borderRadius: 'var(--radius-sm)',
  fontSize: 'var(--text-code)',
  fontWeight: 500,
  fontFamily: 'var(--font-mono)',
  transition: 'all var(--transition-fast)',
} as React.CSSProperties;

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
