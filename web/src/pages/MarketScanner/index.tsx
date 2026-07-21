import { useEffect, useRef, useState } from 'react';
import { Table, Button, Alert, Descriptions } from 'antd';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import FilterToolbar from '@/components/FilterToolbar';
import EmptyState from '@/components/EmptyState';
import ThemeTag from '@/components/ThemeTag';
import { useScanner } from '@/hooks/useScanner';
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion';
import { ReloadOutlined } from '@ant-design/icons';
import type { ScanResult } from '@/types/scanner';

/**
 * Neutral mono count cell for the scan-history table — the + / - / ~
 * prefix carries the meaning (new / delisted / changed) so colour stays
 * reserved for the status column.
 */
function ScanCount({ value, prefix }: { value: number; prefix: string }) {
  return (
    <span
      className={`font-mono tabular-nums ${value > 0 ? 'ad-text-primary' : 'ad-text-tertiary'}`}
    >
      {value > 0 ? `${prefix}${value}` : value}
    </span>
  );
}

export default function MarketScanner() {
  const [lastScan, setLastScan] = useState<ScanResult | null>(null);
  const { logs, isLoading, scan, isScanning } = useScanner();
  // Apple Design #14: drop intro animation entirely when the user prefers
  // reduced motion (and #12 always removes will-change after animationend).
  const prefersReducedMotion = usePrefersReducedMotion();
  const resultWrapperRef = useRef<HTMLDivElement | null>(null);

  const handleScan = async () => {
    try {
      const result = await scan();
      setLastScan(result.data);
    } catch {
      // error handled by mutation
    }
  };

  // Apple Design #11 Frame smoothness: clear will-change as soon as the
  // intro animation finishes so the layer is not kept composited
  // indefinitely. Skip when reduced-motion is requested (no animation runs).
  useEffect(() => {
    if (!lastScan || prefersReducedMotion) return;
    const el = resultWrapperRef.current;
    if (!el) return;
    const onEnd = () => {
      el.style.willChange = 'auto';
      el.removeEventListener('animationend', onEnd);
    };
    el.addEventListener('animationend', onEnd);
    return () => el.removeEventListener('animationend', onEnd);
  }, [lastScan, prefersReducedMotion]);

  const columns = [
    { title: '扫描日期', dataIndex: 'scan_date', width: 120 },
    { title: '新增', dataIndex: 'new_count', width: 80, render: (v: number) => <ScanCount value={v} prefix="+" /> },
    { title: '退市', dataIndex: 'delisted_count', width: 80, render: (v: number) => <ScanCount value={v} prefix="-" /> },
    { title: '变更', dataIndex: 'changed_count', width: 80, render: (v: number) => <ScanCount value={v} prefix="~" /> },
    { title: '状态', dataIndex: 'status', width: 100, render: (v: string) => v === 'success' ? <ThemeTag variant="success">成功</ThemeTag> : <ThemeTag variant="error">失败</ThemeTag> },
  ];

  const result = lastScan;

  return (
    <PageShell maxWidth="wide">
      {/* Apple Design #12 Materials & depth: the scan-result panel materializes
          (slide + fade along a single path, critically-damped --ease-spring,
          damping 1.0) instead of popping in. #14: reduced motion renders it
          instantly and skips the animation entirely. will-change is scoped to
          the animation lifetime and cleared on animationend so we never pay
          for a permanently composited layer. */}
      <style>{`
        @keyframes market-scanner-materialize {
          from { opacity: 0; transform: translateY(8px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .market-scanner-result {
          animation: market-scanner-materialize 0.35s var(--ease-spring) both;
          will-change: transform, opacity;
        }
        .market-scanner-result.is-reduced-motion {
          animation: none;
          will-change: auto;
        }
      `}</style>
      <PageHeader
        title="全市场扫描"
        description="自动发现新增、退市、变更的标的，保持数据库与市场同步"
      />

      <Panel
        className="ad-mb-5"
        title="全市场扫描"
        extra={
          <Button type="primary" icon={<ReloadOutlined />} onClick={handleScan} loading={isScanning}>
            立即扫描
          </Button>
        }
      >
        <p>
          对比 akshare 最新标的列表与数据库，自动发现新增、退市、变更的标的。
          定时任务：每周日凌晨 03:00 自动执行。
        </p>
      </Panel>

      {result && (
        <div
          ref={resultWrapperRef}
          className={`ad-mb-5 market-scanner-result${prefersReducedMotion ? ' is-reduced-motion' : ''}`}
        >
        <Panel
          className="ad-mb-0"
          title={`扫描结果 - ${result.scan_date}`}
        >
          {result.error ? (
            <Alert type="error" message={result.error} />
          ) : (
            <div className="ad-metric-strip">
              {[
                { title: '新增标的', items: result.new, render: (e: any) => `${e.name} (${e.market})` },
                { title: '退市标的', items: result.delisted, render: (e: any) => `${e.name} (${e.market})` },
                { title: '变更标的', items: result.changed, render: (e: any) => Object.entries(e.changes).map(([k, v]: [string, any]) => `${k}: ${v.old} → ${v.new}`).join(', ') },
              ].map((section) => (
                <div
                  key={section.title}
                  className="ad-metric-item"
                >
                  <div className="ad-metric-item__label">
                    {section.title}
                  </div>
                  <Descriptions column={1} size="small">
                    {section.items.length > 0 ? section.items.map((e: any) => (
                      <Descriptions.Item key={e.code} label={e.code}>
                        {section.render(e)}
                      </Descriptions.Item>
                    )) : <Descriptions.Item>无</Descriptions.Item>}
                  </Descriptions>
                </div>
              ))}
            </div>
          )}
        </Panel>
        </div>
      )}

      <Panel title="扫描历史">
        <FilterToolbar total={logs.length}>{null}</FilterToolbar>
        <div className="ad-table-scroll ad-table-sticky">
          <Table
            dataSource={logs}
            columns={columns}
            rowKey="id"
            size="small"
            scroll={{ x: 'max-content' }}
            pagination={{ pageSize: 10 }}
            loading={isLoading}
            locale={{ emptyText: <EmptyState title="暂无扫描历史" /> }}
          />
        </div>
      </Panel>
    </PageShell>
  );
}
