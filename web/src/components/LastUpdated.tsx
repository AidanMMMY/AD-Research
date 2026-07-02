import React, { useEffect, useState } from 'react';
import dayjs from 'dayjs';
import { Tooltip } from 'antd';

/**
 * Renders "更新于 2 分钟前" with the absolute timestamp in the tooltip.
 * Refreshes its relative label every 30s so the value never feels stale.
 *
 * Pass the `dataUpdatedAt` from a React Query result (ms epoch) or a
 * raw ISO string via `iso`. If `loading` is true the label shows
 * "刷新中…" instead so the user knows a fetch is in flight.
 */
export interface LastUpdatedProps {
  /** ms epoch from React Query's dataUpdatedAt. */
  at?: number;
  /** ISO string alternative. Ignored if `at` is provided. */
  iso?: string;
  loading?: boolean;
  /** Override the prefix. Default: "更新于". */
  prefix?: string;
  /** Optional className passthrough. */
  className?: string;
  style?: React.CSSProperties;
}

export default function LastUpdated({
  at,
  iso,
  loading,
  prefix = '更新于',
  className,
  style,
}: LastUpdatedProps) {
  const [, setTick] = useState(0);

  // Re-render every 30s so the relative label keeps moving.
  useEffect(() => {
    const id = window.setInterval(() => setTick((t) => t + 1), 30_000);
    return () => window.clearInterval(id);
  }, []);

  const ts = at ?? (iso ? new Date(iso).getTime() : undefined);
  if (!ts) {
    if (loading) {
      return (
        <span className={className} style={style}>
          刷新中…
        </span>
      );
    }
    return null;
  }

  const absolute = dayjs(ts).format('YYYY-MM-DD HH:mm:ss');
  const diff = dayjs().diff(dayjs(ts), 'minute');
  let relative: string;
  if (diff < 1) relative = '刚刚';
  else if (diff < 60) relative = `${diff} 分钟前`;
  else if (diff < 60 * 24) relative = `${Math.floor(diff / 60)} 小时前`;
  else relative = dayjs(ts).format('MM-DD HH:mm');

  return (
    <Tooltip title={absolute}>
      <span
        className={className ? `${className} last-updated` : 'last-updated'}
        style={style}
        aria-label={`${prefix} ${absolute}`}
      >
        {prefix} {relative}
      </span>
    </Tooltip>
  );
}