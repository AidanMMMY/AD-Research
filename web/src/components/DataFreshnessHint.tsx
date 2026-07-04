import { Tooltip } from 'antd';
import { useEffect, useState } from 'react';

interface Props {
  /** ISO 时间戳或 Date */
  at: string | Date | number | null | undefined;
  /** 提示文本前缀，默认 "数据时间" */
  prefix?: string;
}

/**
 * 统一的"数据新鲜度"小灰字角标。
 * - 相对时间：刚刚 / 5 分钟前 / 3 小时前 / 2 天前
 * - 点击 Tooltip 显示完整本地时间 + "是否仍在更新"
 */
export default function DataFreshnessHint({ at, prefix = '数据时间' }: Props) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(t);
  }, []);

  if (at == null) {
    return <span className="ad-text-xs ad-text-muted">数据时间 —</span>;
  }

  const ts =
    typeof at === 'string'
      ? new Date(at).getTime()
      : typeof at === 'number'
        ? at
        : at.getTime();
  const ago = Math.max(0, Math.round((now - ts) / 60_000));
  const relative =
    ago < 1
      ? '刚刚'
      : ago < 60
        ? `${ago} 分钟前`
        : ago < 60 * 24
          ? `${Math.floor(ago / 60)} 小时前`
          : `${Math.floor(ago / (60 * 24))} 天前`;
  const full = new Date(ts).toLocaleString();

  return (
    <Tooltip title={`${full} · 仍在持续更新`}>
      <span className="ad-text-xs ad-text-muted data-freshness-hint">
        {prefix} {relative}
      </span>
    </Tooltip>
  );
}