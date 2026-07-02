import { useState } from 'react';
import { Table, Button, Alert, Descriptions } from 'antd';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import FilterToolbar from '@/components/FilterToolbar';
import EmptyState from '@/components/EmptyState';
import ThemeTag from '@/components/ThemeTag';
import { useScanner } from '@/hooks/useScanner';
import { ReloadOutlined } from '@ant-design/icons';
import type { ScanResult } from '@/types/scanner';

export default function MarketScanner() {
  const [lastScan, setLastScan] = useState<ScanResult | null>(null);
  const { logs, isLoading, scan, isScanning } = useScanner();

  const handleScan = async () => {
    try {
      const result = await scan();
      setLastScan(result.data);
    } catch {
      // error handled by mutation
    }
  };

  const columns = [
    { title: '扫描日期', dataIndex: 'scan_date', width: 120 },
    { title: '新增', dataIndex: 'new_count', width: 80, render: (v: number) => v > 0 ? <ThemeTag variant="rise">+{v}</ThemeTag> : <ThemeTag variant="default">{v}</ThemeTag> },
    { title: '退市', dataIndex: 'delisted_count', width: 80, render: (v: number) => v > 0 ? <ThemeTag variant="fall">-{v}</ThemeTag> : <ThemeTag variant="default">{v}</ThemeTag> },
    { title: '变更', dataIndex: 'changed_count', width: 80, render: (v: number) => v > 0 ? <ThemeTag variant="warning">~{v}</ThemeTag> : <ThemeTag variant="default">{v}</ThemeTag> },
    { title: '状态', dataIndex: 'status', width: 100, render: (v: string) => v === 'success' ? <ThemeTag variant="success">成功</ThemeTag> : <ThemeTag variant="error">失败</ThemeTag> },
  ];

  const result = lastScan;

  return (
    <PageShell maxWidth="wide">
      <PageHeader
        title="全市场扫描"
        description="自动发现新增、退市、变更的标的，保持数据库与市场同步"
      />

      <div className="phase5c-section">
        <Panel
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
      </div>

      {result && (
        <div className="phase5c-section">
          <Panel title={`扫描结果 - ${result.scan_date}`}>
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

      <div className="phase5c-section">
        <Panel title="扫描历史">
          <FilterToolbar total={logs.length}>{null}</FilterToolbar>
          <div className="ad-density-dense ad-table-scroll ad-table-sticky">
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
      </div>
    </PageShell>
  );
}
