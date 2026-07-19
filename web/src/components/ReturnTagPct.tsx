import { ArrowUpOutlined, ArrowDownOutlined, MinusOutlined } from '@ant-design/icons';
import { formatPercentRaw, NULL_PLACEHOLDER } from '@/utils/format';

interface ReturnTagPctProps {
  value?: number | null;
}

/**
 * ReturnTagPct — 与 ReturnTag 视觉一致，但内部走 ``formatPercentRaw``
 * （不 ×100），用于显示后端 ``change_pct`` / ``settle_change_pct`` 之类
 * "已乘 100 的百分比本身" 字段。
 *
 * 什么时候用哪个：
 *
 * | 字段语义                | 组件                | 函数              |
 * |-------------------------|---------------------|-------------------|
 * | 小数 (0.025 = 2.5%)     | ``<ReturnTag>``     | ``formatPercent`` |
 * | 百分比 (1.5 = 1.5%)     | ``<ReturnTagPct>``  | ``formatPercentRaw`` |
 *
 * 用错会导致涨跌幅被错误放大 100 倍（参见 2026-07-19 首页市场脉搏 bug）。
 */
function getArrow(value: number | null | undefined) {
  if (value === undefined || value === null || value === 0) {
    return <MinusOutlined className="return-tag__arrow" aria-label="flat" />;
  }
  return value > 0 ? (
    <ArrowUpOutlined className="return-tag__arrow" aria-label="up" />
  ) : (
    <ArrowDownOutlined className="return-tag__arrow" aria-label="down" />
  );
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

export default function ReturnTagPct({ value }: ReturnTagPctProps) {
  if (value === undefined || value === null) {
    return (
      <span className="return-tag return-tag--empty tabular-nums">
        {NULL_PLACEHOLDER}
      </span>
    );
  }

  return (
    <span className={`return-tag tabular-nums ${getVariantClass(value)}`}>
      {getArrow(value)}
      {formatPercentRaw(value)}
    </span>
  );
}
