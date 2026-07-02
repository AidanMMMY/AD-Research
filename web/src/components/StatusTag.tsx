import { Tag } from 'antd';

interface StatusTagProps {
  status: string;
}

interface StatusConfig {
  label: string;
  color: string;
  bg: string;
  border: string;
}

const STATUS_MAP: Record<string, StatusConfig> = {
  success: {
    label: '成功',
    color: 'var(--color-success)',
    bg: 'var(--color-success-dim)',
    border: 'var(--color-success-border)',
  },
  running: {
    label: '运行中',
    color: 'var(--color-warning)',
    bg: 'var(--color-warning-dim)',
    border: 'var(--color-warning-border)',
  },
  failed: {
    label: '失败',
    color: 'var(--color-error)',
    bg: 'var(--color-error-dim)',
    border: 'var(--color-error-border)',
  },
  pending: {
    label: '等待中',
    color: 'var(--text-tertiary)',
    bg: 'var(--bg-hover)',
    border: 'var(--border-default)',
  },
};

export default function StatusTag({ status }: StatusTagProps) {
  const normalized = status?.toLowerCase() ?? 'pending';
  const config = STATUS_MAP[normalized] || {
    label: status || '未知',
    color: 'var(--text-secondary)',
    bg: 'var(--bg-hover)',
    border: 'var(--border-default)',
  };

  return (
    <Tag
      className="status-tag"
      style={{
        color: config.color,
        background: config.bg,
        borderColor: config.border,
      }}
    >
      {config.label}
    </Tag>
  );
}
