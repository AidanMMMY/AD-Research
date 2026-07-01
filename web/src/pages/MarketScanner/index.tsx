import { useState } from 'react';
import { Table, Button, Alert, Descriptions } from 'antd';
import Panel from '@/components/Panel';
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
    <div>
      <h1 style={{ fontSize: 'var(--text-h1-size)', fontWeight: 500, color: 'var(--text-primary)', margin: '0 0 8px', letterSpacing: '-0.03em' }}>全市场扫描</h1>
      <p style={{ margin: '0 0 32px', color: 'var(--text-tertiary)', fontSize: 'var(--text-body-size)' }}>自动发现新增、退市、变更的标的，保持数据库与市场同步</p>
      <Panel
        title="全市场扫描"
        extra={
          <Button type="primary" icon={<ReloadOutlined />} onClick={handleScan} loading={isScanning}>
            立即扫描
          </Button>
        }
        variant="minimal"
        style={{ marginBottom: 16 }}
      >
        <p style={{ color: 'var(--text-secondary)' }}>
          对比 akshare 最新标的列表与数据库，自动发现新增、退市、变更的标的。
          定时任务：每周日凌晨 03:00 自动执行。
        </p>
      </Panel>

      {result && (
        <Panel title={`扫描结果 - ${result.scan_date}`} variant="minimal" style={{ marginBottom: 16 }}>
          {result.error ? (
            <Alert type="error" message={result.error} />
          ) : (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(3, 1fr)',
                borderTop: '1px solid var(--border-default)',
                borderBottom: '1px solid var(--border-default)',
              }}
            >
              {[
                { title: '新增标的', items: result.new, render: (e: any) => `${e.name} (${e.market})` },
                { title: '退市标的', items: result.delisted, render: (e: any) => `${e.name} (${e.market})` },
                { title: '变更标的', items: result.changed, render: (e: any) => Object.entries(e.changes).map(([k, v]: [string, any]) => `${k}: ${v.old} → ${v.new}`).join(', ') },
              ].map((section, i) => (
                <div
                  key={section.title}
                  style={{
                    padding: '16px',
                    borderRight: i < 2 ? '1px solid var(--border-default)' : 'none',
                  }}
                >
                  <div
                    style={{
                      fontSize: 'var(--text-label-size)',
                      color: 'var(--text-tertiary)',
                      fontWeight: 500,
                      textTransform: 'uppercase',
                      letterSpacing: '0.08em',
                      marginBottom: 12,
                    }}
                  >
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
      )}

      <Panel title="扫描历史" variant="minimal">
        <Table
          dataSource={logs}
          columns={columns}
          rowKey="id"
          size="small"
          scroll={{ x: 'max-content' }}
          pagination={{ pageSize: 10 }}
          loading={isLoading}
        />
      </Panel>
    </div>
  );
}
