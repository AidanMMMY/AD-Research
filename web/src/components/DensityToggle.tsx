import { Segmented } from 'antd';
import { useDensity, type Density } from '@/hooks/useDensity';

const OPTIONS: { label: string; value: Density }[] = [
  { label: '紧凑', value: 'dense' },
  { label: '适中', value: 'comfortable' },
  { label: '宽松', value: 'spacious' },
];

export default function DensityToggle() {
  const { density, setDensity } = useDensity();
  return (
    <Segmented
      value={density}
      onChange={(v) => setDensity(v as Density)}
      options={OPTIONS}
      size="small"
      style={{ background: 'var(--bg-hover)', borderRadius: 10 }}
    />
  );
}