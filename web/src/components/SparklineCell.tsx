import { useSparkline } from '@/hooks/useSparkline';
import Sparkline from '@/components/Sparkline';

export interface SparklineCellProps {
  code: string;
  /** Number of days for the sparkline. Default: 30. */
  days?: number;
}

/**
 * Row-level sparkline cell for list tables.
 * Owns its own useSparkline query so per-row caching works
 * without re-fetching the whole list.
 */
export default function SparklineCell({ code, days = 30 }: SparklineCellProps) {
  const { data } = useSparkline({ code, days });
  if (!data || !data.points || data.points.length === 0) {
    return <span className="mobile-list-item__meta">-</span>;
  }
  return <Sparkline data={data.points} width={80} height={20} />;
}
