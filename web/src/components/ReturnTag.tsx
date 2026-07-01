import type { CSSProperties } from 'react';
import { ArrowUpOutlined, ArrowDownOutlined, MinusOutlined } from '@ant-design/icons';
import { getReturnColor, getReturnBgColor, getReturnBorderColor } from '@/utils/color';
import { formatPercent } from '@/utils/format';
import { useSettingsStore } from '@/stores/settings';

interface ReturnTagProps {
  value?: number | null;
}

const baseStyle: CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 2,
  padding: '2px 8px',
  borderRadius: 'var(--radius-sm)',
  fontSize: 'var(--text-code-size)',
  fontWeight: 500,
  fontFamily: 'var(--font-mono)',
  transition: 'background var(--transition-fast), color var(--transition-fast), border-color var(--transition-fast)',
};

function getArrow(value: number | null | undefined) {
  if (value === undefined || value === null || value === 0) {
    return <MinusOutlined style={{ fontSize: '0.85em' }} aria-label="flat" />;
  }
  return value > 0
    ? <ArrowUpOutlined style={{ fontSize: '0.85em' }} aria-label="up" />
    : <ArrowDownOutlined style={{ fontSize: '0.85em' }} aria-label="down" />;
}

export default function ReturnTag({ value }: ReturnTagProps) {
  const colorConvention = useSettingsStore((s) => s.colorConvention);

  if (value === undefined || value === null) {
    return (
      <span
        className="tabular-nums"
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
      className="tabular-nums"
      style={{
        ...baseStyle,
        color: getReturnColor(value, colorConvention),
        background: getReturnBgColor(value, colorConvention),
        border: `1px solid ${getReturnBorderColor(value, colorConvention)}`,
      }}
    >
      {getArrow(value)}
      {formatPercent(value)}
    </span>
  );
}
