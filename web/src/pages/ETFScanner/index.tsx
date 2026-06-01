import { useState } from 'react';
import { Card, Table, Button, Tag, Alert, Descriptions, Row, Col } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { ReloadOutlined } from '@ant-design/icons';

interface ScanResult {
  success: boolean;
  new: { code: string; name: string; market: string }[];
  delisted: { code: string; name: string; market: string }[];
  changed: { code: string; changes: Record<string, { old: string; new: string }> }[];
  scan_date: string;
  error?: string;
}

export default function ETFScanner() {
  const [lastScan, setLastScan] = useState<ScanResult | null>(null);

  const { data: logs, isLoading: logsLoading, refetch: refetchLogs } = useQuery({
    queryKey: ['etf-scan-logs'],
    queryFn: async () => {
      const res = await fetch('/api/v1/etfs/scan/logs');
      return res.json();
    },
    staleTime: 60_000,
  });

  const handleScan = async () => {
    const res = await fetch('/api/v1/etfs/scan', { method: 'POST' });
    const result = await res.json();
    setLastScan(result);
    refetchLogs();
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
      <Card title="全市场ETF扫描" extra={
        <Button type="primary" icon={<ReloadOutlined />} onClick={handleScan}>
          立即扫描
        </Button>
      } style={{ marginBottom: 16 }}>
        <p style={{ color: '#666' }}>
          对比 akshare 最新ETF列表与数据库，自动发现新增、退市、变更的ETF。
          定时任务：每周日凌晨 03:00 自动执行。
        </p>
      </Card>

      {result && (
        <Card title={`扫描结果 - ${result.scan_date}`} style={{ marginBottom: 16 }}>
          {result.error ? (
            <Alert type="error" message={result.error} />
          ) : (
            <>
              <Row gutter={[16, 16]}>
                <Col xs={24} md={8}>
                  <Card size="small">
                    <Descriptions title="新增ETF" column={1} size="small">
                      {result.new.length > 0 ? result.new.map((e) => (
                        <Descriptions.Item key={e.code} label={e.code}>
                          {e.name} ({e.market})
                        </Descriptions.Item>
                      )) : <Descriptions.Item>无</Descriptions.Item>}
                    </Descriptions>
                  </Card>
                </Col>
                <Col xs={24} md={8}>
                  <Card size="small">
                    <Descriptions title="退市ETF" column={1} size="small">
                      {result.delisted.length > 0 ? result.delisted.map((e) => (
                        <Descriptions.Item key={e.code} label={e.code}>
                          {e.name} ({e.market})
                        </Descriptions.Item>
                      )) : <Descriptions.Item>无</Descriptions.Item>}
                    </Descriptions>
                  </Card>
                </Col>
                <Col xs={24} md={8}>
                  <Card size="small">
                    <Descriptions title="变更ETF" column={1} size="small">
                      {result.changed.length > 0 ? result.changed.map((e) => (
                        <Descriptions.Item key={e.code} label={e.code}>
                          {Object.entries(e.changes).map(([k, v]) => `${k}: ${v.old} → ${v.new}`).join(', ')}
                        </Descriptions.Item>
                      )) : <Descriptions.Item>无</Descriptions.Item>}
                    </Descriptions>
                  </Card>
                </Col>
              </Row>
            </>
          )}
        </Card>
      )}

      <Card title="扫描历史">
        <Table
          dataSource={logs || []}
          columns={columns}
          rowKey="id"
          size="small"
          pagination={{ pageSize: 10 }}
          loading={logsLoading}
        />
      </Card>
    </div>
  );
}
