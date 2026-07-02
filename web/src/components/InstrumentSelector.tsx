import { useMemo, useState } from 'react';
import { Select, Button, Space, message } from 'antd';
import { FolderOpenOutlined } from '@ant-design/icons';
import ThemeTag from '@/components/ThemeTag';
import { useInstrumentList } from '@/hooks/useInstrumentList';
import { usePoolList } from '@/hooks/usePoolDetail';

const PRESET_TOP_N = 4;

interface InstrumentItem {
  code: string;
  name: string;
  category?: string;
  fund_size?: number;
}

interface InstrumentSelectorProps {
  value: string[];
  onChange: (codes: string[]) => void;
  maxCount?: number;
  showPresets?: boolean;
  showPoolImport?: boolean;
  showClear?: boolean;
}

export default function InstrumentSelector({
  value,
  onChange,
  maxCount = 10,
  showPresets = true,
  showPoolImport = true,
  showClear = true,
}: InstrumentSelectorProps) {
  const [showAllPresets, setShowAllPresets] = useState(false);

  const { data: instrumentList } = useInstrumentList({ page_size: 10000 });
  const { data: pools, isLoading: poolsLoading } = usePoolList();

  const presetGroups = useMemo(() => {
    const items: InstrumentItem[] = instrumentList?.items || [];
    const byCategory: Record<string, InstrumentItem[]> = {};
    items.forEach((item) => {
      const category = item.category || '未分类';
      if (!byCategory[category]) byCategory[category] = [];
      byCategory[category].push(item);
    });

    return Object.entries(byCategory)
      .sort(([a], [b]) => a.localeCompare(b, 'zh-CN'))
      .map(([category, members]) => ({
        label: category,
        codes: members
          .sort((a, b) => (b.fund_size || 0) - (a.fund_size || 0))
          .slice(0, PRESET_TOP_N)
          .map((item) => item.code),
      }))
      .filter((group) => group.codes.length > 0);
  }, [instrumentList]);

  const visiblePresetGroups = useMemo(() => {
    if (showAllPresets) return presetGroups;
    return presetGroups.slice(0, 8);
  }, [presetGroups, showAllPresets]);

  const instrumentOptions = (instrumentList?.items || []).map((item) => ({
    label: `${item.code} ${item.name}`,
    value: item.code,
  }));

  const poolOptions = (pools || []).map((pool) => ({
    label: `${pool.name} (${pool.members?.length || 0}只)`,
    value: pool.id,
    codes: (pool.members || []).map((m) => m.etf_code),
  }));

  const handleSelectChange = (codes: string[]) => {
    if (codes.length > maxCount) {
      message.warning(`最多选择${maxCount}只标的`);
      return;
    }
    onChange(codes);
  };

  const handleAddPreset = (codes: string[]) => {
    const newCodes = Array.from(new Set([...value, ...codes]));
    if (newCodes.length > maxCount) {
      message.warning(`最多选择${maxCount}只标的`);
      return;
    }
    onChange(newCodes);
  };

  const handleSelectPool = (poolId: number | undefined) => {
    if (!poolId) return;
    const pool = poolOptions.find((p) => p.value === poolId);
    if (!pool) return;
    const newCodes = Array.from(new Set([...value, ...pool.codes]));
    if (newCodes.length > maxCount) {
      message.warning(`标的池成员数量较多，仅添加前${maxCount}只`);
      onChange(newCodes.slice(0, maxCount));
      return;
    }
    onChange(newCodes);
    message.success(`已添加「${pool.label}」中的 ${pool.codes.length} 只标的`);
  };

  const handleRemoveCode = (code: string) => {
    onChange(value.filter((c) => c !== code));
  };

  return (
    <div>
      <div className="instrument-selector__label">
        选择标的（{value.length}/{maxCount}）：
      </div>
      <Select
        mode="multiple"
        showSearch
        placeholder="搜索并选择标的"
        value={value}
        onChange={handleSelectChange}
        options={instrumentOptions}
        style={{ width: '100%' }}
        maxTagCount={0}
        tagRender={() => <span />}
        filterOption={(input, option) =>
          (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
        }
      />
      {value.length > 0 && (
        <div className="instrument-selector__tags">
          <Space size={[8, 8]} wrap>
            {value.map((code) => (
              <ThemeTag key={code} variant="accent" className="instrument-selector__tag">
                {code}
                <span
                  className="instrument-selector__remove"
                  onClick={() => handleRemoveCode(code)}
                >
                  ×
                </span>
              </ThemeTag>
            ))}
          </Space>
        </div>
      )}

      {(showPresets || showPoolImport || showClear) && (
        <div className="instrument-selector__presets">
          <span className="instrument-selector__presets-label">快速选择：</span>
          <Space size={[8, 8]} wrap>
            {showPresets &&
              visiblePresetGroups.map((group) => (
                <Button key={group.label} size="small" onClick={() => handleAddPreset(group.codes)}>
                  +{group.label}
                </Button>
              ))}
            {showPresets && presetGroups.length > 8 && (
              <Button size="small" type="link" onClick={() => setShowAllPresets((v) => !v)}>
                {showAllPresets ? '收起' : `更多 (${presetGroups.length - 8})`}
              </Button>
            )}
            {showPoolImport && (
              <Select
                size="small"
                placeholder={
                  <span>
                    <FolderOpenOutlined /> 从标的池导入
                  </span>
                }
                className="instrument-selector__pool-select"
                loading={poolsLoading}
                onChange={handleSelectPool}
                options={poolOptions}
                allowClear
              />
            )}
            {showClear && (
              <Button size="small" danger onClick={() => onChange([])}>
                清空
              </Button>
            )}
          </Space>
        </div>
      )}
    </div>
  );
}
