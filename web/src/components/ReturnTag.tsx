import { ArrowUpOutlined, ArrowDownOutlined, MinusOutlined } from '@ant-design/icons';
import { formatPercent } from '@/utils/format';
import { useSettingsStore } from '@/stores/settings';

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

function getVariantClass(value: number, colorConvention: 'china' | 'us'): string {
  if (value === 0) {
    return 'return-tag--flat';
  }
  // China convention: 红涨绿跌 → positive uses rise, negative uses fall.
  // US convention: 绿涨红跌 → flipped.
  if (value > 0) {
    return colorConvention === 'us' ? 'return-tag--fall' : 'return-tag--rise';
  }
  return colorConvention === 'us' ? 'return-tag--rise' : 'return-tag--fall';
}

/**
 * 涨跌幅色块 — 跟随全局 --color-rise / --color-fall token，自动响应
 * China/US 颜色约定切换 (settings.colorConvention) 与 light/dark 主题。
 */
export default function ReturnTag({ value }: ReturnTagProps) {
  const colorConvention = useSettingsStore((s) => s.colorConvention);

  if (value === undefined || value === null) {
    return (
      <span className="return-tag return-tag--empty tabular-nums">
        -
      </span>
    );
  }

  return (
    <span className={`return-tag tabular-nums ${getVariantClass(value, colorConvention)}`}>
      {getArrow(value)}
      {formatPercent(value)}
    </span>
  );
}