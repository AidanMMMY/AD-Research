import { ArrowUpOutlined, ArrowDownOutlined, MinusOutlined } from '@ant-design/icons';
import { formatPercent } from '@/utils/format';

interface ReturnTagProps {
  value?: number | null;
}

function getArrow(value: number | null | undefined) {
  if (value === undefined || value === null || value === 0) {
    return <MinusOutlined className="return-tag__arrow" aria-label="flat" />;
  }
  return value > 0
    ? <ArrowUpOutlined className="return-tag__arrow" aria-label="up" />
    : <ArrowDownOutlined className="return-tag__arrow" aria-label="down" />;
}

function getVariantClass(value: number): string {
  if (value === 0) {
    return 'return-tag--flat';
  }
  // CSS variables --color-rise / --color-fall already swap via
  // [data-color-convention] on <html>, so positive always maps to rise
  // and negative always maps to fall.
  return value > 0 ? 'return-tag--rise' : 'return-tag--fall';
}

/**
 * 涨跌幅色块 — 跟随全局 --color-rise / --color-fall token，自动响应
 * China/US 颜色约定切换 (settings.colorConvention) 与 light/dark 主题。
 */
export default function ReturnTag({ value }: ReturnTagProps) {
  if (value === undefined || value === null) {
    return (
      <span className="return-tag return-tag--empty tabular-nums">
        -
      </span>
    );
  }

  return (
    <span className={`return-tag tabular-nums ${getVariantClass(value)}`}>
      {getArrow(value)}
      {formatPercent(value)}
    </span>
  );
}