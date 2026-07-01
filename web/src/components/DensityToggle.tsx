import { Segmented, Tooltip } from 'antd';
import { useDensity, type Density } from '@/hooks/useDensity';

const OPTIONS: { label: string; value: Density; description: string }[] = [
  { label: '紧凑', value: 'dense', description: '紧凑模式：表格行高 32px，一屏显示更多数据' },
  { label: '适中', value: 'comfortable', description: '适中模式：表格行高 40px，平衡信息密度与可读性' },
  { label: '宽松', value: 'spacious', description: '宽松模式：表格行高 52px，长时间阅读更舒适' },
];

const GROUP_DESCRIPTION = '切换表格与列表的显示密度，影响全站数据密集度';

export default function DensityToggle() {
  const { density, setDensity } = useDensity();
  return (
    <Tooltip title={GROUP_DESCRIPTION} placement="bottom">
      <Segmented
        value={density}
        onChange={(v) => setDensity(v as Density)}
        options={OPTIONS.map((o) => ({
          label: (
            <Tooltip title={o.description} placement="bottom">
              <span>{o.label}</span>
            </Tooltip>
          ),
          value: o.value,
        }))}
        size="small"
        style={{ background: 'var(--bg-hover)', borderRadius: 10 }}
        aria-label={GROUP_DESCRIPTION}
      />
    </Tooltip>
  );
}