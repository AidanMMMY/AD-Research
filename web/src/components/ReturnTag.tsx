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
  if (value > 0) {
    return colorConvention === 'us' ? 'return-tag--fall' : 'return-tag--rise';
  }
  return colorConvention === 'us' ? 'return-tag--rise' : 'return-tag--fall';
}

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
