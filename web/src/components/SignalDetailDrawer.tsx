import { Drawer, Descriptions, Tag } from 'antd';
import type { Signal } from '@/types/signal';
import { useIsMobile } from '@/hooks/useBreakpoint';
import { useFocusRestore } from '@/hooks/useFocusRestore';

interface Props {
  signal: Signal | null;
  onClose: () => void;
}

const SIGNAL_TYPE_COLOR: Record<string, string> = {
  BUY: 'success',
  SELL: 'error',
  HOLD: 'default',
};

/**
 * Read-only drawer that surfaces the fields that matter most for "why did
 * this signal fire?". Currently shows the signal's metadata plus a
 * prominent disclaimer explaining the data lineage and known caveats.
 *
 * The detailed "历史胜率 / 平均持有期" stats are intentionally NOT yet
 * surfaced because the upstream `score_history` endpoint isn't wired in
 * here — once it is, we should populate the "依据" section with real
 * numbers rather than the placeholder copy.
 */
export default function SignalDetailDrawer({ signal, onClose }: Props) {
  const isMobile = useIsMobile();
  // WCAG 2.4.3: when the drawer closes, return keyboard focus to the
  // signal row in the dashboard table that opened it.
  useFocusRestore(!!signal);
  if (!signal) return null;

  const signalType = signal.signal_type;
  return (
    <Drawer
      title={`信号详情 · ${signal.etf_code || ''}`}
      open={!!signal}
      onClose={onClose}
      width={isMobile ? '100%' : 520}
      destroyOnClose
    >
      <Descriptions column={1} bordered size="small">
        <Descriptions.Item label="触发时间">
          {signal.trade_date || signal.created_at?.slice(0, 16) || '—'}
        </Descriptions.Item>
        <Descriptions.Item label="策略 ID">
          {signal.strategy_id}
        </Descriptions.Item>
        <Descriptions.Item label="策略名">
          {signal.strategy_name || '—'}
        </Descriptions.Item>
        <Descriptions.Item label="策略家族">
          {signal.strategy_type || '—'}
        </Descriptions.Item>
        <Descriptions.Item label="标的">
          {signal.etf_code}
          {signal.etf_name ? ` · ${signal.etf_name}` : ''}
        </Descriptions.Item>
        <Descriptions.Item label="信号类型">
          <Tag color={SIGNAL_TYPE_COLOR[signalType] || 'default'}>
            {signalType}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="信号强度">
          {signal.strength ?? '—'}
        </Descriptions.Item>
        <Descriptions.Item label="依据">
          <span className="signal-detail-disclaimer">
            此信号由策略{' '}
            <code>
              {signal.strategy_name || signal.strategy_id}
            </code>{' '}
            在样本期内基于历史胜率统计生成。
            详细回测胜率、平均持有期、最大回撤等指标将在 <code>score_history</code>{' '}
            接口返回后接入展示（待接入）。
            <br />
            <br />
            <strong className="signal-detail-warning">仅供研究参考，不构成投资建议。</strong>
          </span>
        </Descriptions.Item>
      </Descriptions>
    </Drawer>
  );
}