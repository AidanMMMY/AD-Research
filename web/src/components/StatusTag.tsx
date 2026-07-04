import { Tag } from 'antd';

interface StatusTagProps {
  status: string;
}

const STATUS_LABELS: Record<string, string> = {
  success: '成功',
  running: '运行中',
  failed: '失败',
  pending: '等待中',
};

export default function StatusTag({ status }: StatusTagProps) {
  const normalized = status?.toLowerCase() ?? 'pending';
  const statusClass = STATUS_LABELS[normalized] ? normalized : 'unknown';
  const label = STATUS_LABELS[normalized] ?? (status || '未知');

  return (
    <Tag className={`status-tag status-tag--${statusClass}`}>
      {label}
    </Tag>
  );
}
