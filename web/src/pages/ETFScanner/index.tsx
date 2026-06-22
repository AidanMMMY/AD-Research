import { useState } from 'react';
import { Table, Button, Tag, Alert, Descriptions, Row, Col } from 'antd';
import GlassCard from '@/components/GlassCard';
import { useScanner } from '@/hooks/useScanner';
import { ReloadOutlined } from '@ant-design/icons';
import type { ScanResult } from '@/types/scanner';

export default function ETFScanner() {
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
    { title: '新增', dataIndex: 'new_count', width: 80, render: (v: number) => v > 0 ? <Tag color="green">+{v}</Tag> : <Tag>{v}</Tag> },
    { title: '退市', dataIndex: 'delisted_count', width: 80, render: (v: number) => v > 0 ? <Tag color="red">-{v}</Tag> : <Tag>{v}</Tag> },
    { title: '变更', dataIndex: 'changed_count', width: 80, render: (v: number) => v > 0 ? <Tag color="orange">~{v}</Tag> : <Tag>{v}</Tag> },
    { title: '状态', dataIndex: 'status', width: 100, render: (v: string) => v === 'success' ? <Tag color="success">成功</Tag> : <Tag color="error">失败</Tag> },
  ];

  const result = lastScan;

  return (
    <div>
      <GlassCard title="全市场ETF扫描" extra={
        <Button type="primary" icon={<ReloadOutlined />} onClick={handleScan} loading={isScanning}>
          立即扫描
        </Button>
      } style={{ marginBottom: 16 }}>
        <p style={{ color: '#94a3b8' }}>
          对比 akshare 最新ETF列表与数据库，自动发现新增、退市、变更的ETF。
          定时任务：每周日凌晨 03:00 自动执行。
        </p>
      </GlassCard>

      {result && (
        <GlassCard title={`扫描结果 - ${result.scan_date}`} style={{ marginBottom: 16 }}>
          {result.error ? (
            <Alert type="error" message={result.error} />
          ) : (
            <>
              <Row gutter={[16, 16]}>
                <Col xs={24} md={8}>
                  <GlassCard padding="sm">
                    <Descriptions title="新增ETF" column={1} size="small">
                      {result.new.length > 0 ? result.new.map((e) => (
                        <Descriptions.Item key={e.code} label={e.code}>
                          {e.name} ({e.market})
                        </Descriptions.Item>
                      )) : <Descriptions.Item>无</Descriptions.Item>}
                    </Descriptions>
                  </GlassCard>
                </Col>
                <Col xs={24} md={8}>
                  <GlassCard padding="sm">
                    <Descriptions title="退市ETF" column={1} size="small">
                      {result.delisted.length > 0 ? result.delisted.map((e) => (
                        <Descriptions.Item key={e.code} label={e.code}>
                          {e.name} ({e.market})
                        </Descriptions.Item>
                      )) : <Descriptions.Item>无</Descriptions.Item>}
                    </Descriptions>
                  </GlassCard>
                </Col>
                <Col xs={24} md={8}>
                  <GlassCard padding="sm">
                    <Descriptions title="变更ETF" column={1} size="small">
                      {result.changed.length > 0 ? result.changed.map((e) => (
                        <Descriptions.Item key={e.code} label={e.code}>
                          {Object.entries(e.changes).map(([k, v]) => `${k}: ${v.old} → ${v.new}`).join(', ')}
                        </Descriptions.Item>
                      )) : <Descriptions.Item>无</Descriptions.Item>}
                    </Descriptions>
                  </GlassCard>
                </Col>
              </Row>
            </>
          )}
        </GlassCard>
      )}

      <GlassCard title="扫描历史">
        <Table
          dataSource={logs}
          columns={columns}
          rowKey="id"
          size="small"
          pagination={{ pageSize: 10 }}
          loading={isLoading}
        />
      </GlassCard>
    </div>
  );
}
