import { useMemo } from 'react';
import { Card, Row, Col, Table, Spin, Tag, Statistic, Alert, Space } from 'antd';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { useSectorRotation } from '@/hooks/useSectorRotation';
import ReturnTag from '@/components/ReturnTag';

export default function SectorRotation() {
  const { data, isLoading } = useSectorRotation();

  const sectors = data?.sectors || [];
  const signals = data?.rotation_signals || [];
  const marketAvg = data?.market_avg;

  const barOption: EChartsOption = useMemo(() => {
    return {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: 80, right: 20, top: 20, bottom: 30 },
      xAxis: { type: 'value', axisLabel: { formatter: '{value}%' } },
      yAxis: {
        type: 'category',
        data: [...sectors].reverse().map((s) => s.category),
        axisLabel: { fontSize: 11 },
      },
      series: [
        {
          type: 'bar',
          data: [...sectors].reverse().map((s) => ({
            value: s.return_1m,
            itemStyle: { color: s.return_1m >= 0 ? '#cf1322' : '#3f8600' },
          })),
          label: { show: true, formatter: '{c}%', fontSize: 10 },
        },
      ],
    };
  }, [sectors]);

  const rsOption: EChartsOption = useMemo(() => {
    return {
      tooltip: { trigger: 'axis' },
      grid: { left: 60, right: 20, top: 30, bottom: 60 },
      xAxis: {
        type: 'category',
        data: sectors.map((s) => s.category),
        axisLabel: { rotate: 45, fontSize: 10 },
      },
      yAxis: { type: 'value', name: '相对强弱' },
      series: [
        {
          type: 'bar',
          data: sectors.map((s) => ({
            value: s.relative_strength_1m,
            itemStyle: { color: s.relative_strength_1m >= 1 ? '#cf1322' : '#3f8600' },
          })),
          markLine: { data: [{ yAxis: 1, label: { formatter: '市场平均' } }] },
        },
      ],
    };
  }, [sectors]);

  const columns = [
    { title: '排名', dataIndex: 'momentum_rank', width: 60 },
    { title: '板块', dataIndex: 'category' },
    { title: 'ETF数量', dataIndex: 'count', width: 80 },
    {
      title: '1月收益',
      dataIndex: 'return_1m',
      render: (v: number) => <ReturnTag value={v} />,
      width: 100,
    },
    {
      title: '3月收益',
      dataIndex: 'return_3m',
      render: (v: number) => <ReturnTag value={v} />,
      width: 100,
    },
    { title: '夏普', dataIndex: 'sharpe_1y', width: 80 },
    { title: '波动率', dataIndex: 'volatility_20d', render: (v: number) => `${(v * 100).toFixed(1)}%`, width: 90 },
    { title: 'RSI', dataIndex: 'rsi14', width: 70 },
    {
      title: '相对强弱',
      dataIndex: 'relative_strength_1m',
      render: (v: number) => (
        <Tag color={v >= 1 ? 'red' : 'green'}>{v.toFixed(2)}</Tag>
      ),
      width: 100,
    },
  ];

  return (
    <div>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} md={8}>
          <Card>
            <Statistic
              title="分析日期"
              value={data?.trade_date || '-'}
            />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card>
            <Statistic
              title="市场平均1月收益"
              value={marketAvg?.return_1m ?? 0}
              precision={2}
              suffix="%"
              valueStyle={{ color: (marketAvg?.return_1m || 0) >= 0 ? '#cf1322' : '#3f8600' }}
            />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card>
            <Statistic
              title="板块数量"
              value={sectors.length}
            />
          </Card>
        </Col>
      </Row>

      {signals.length > 0 && (
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col span={24}>
            <Card title="轮动信号" size="small">
              <Space direction="vertical" style={{ width: '100%' }}>
                {signals.map((signal, idx) => (
                  <Alert
                    key={idx}
                    message={signal.message}
                    type={signal.type === 'up' ? 'success' : 'warning'}
                    showIcon
                  />
                ))}
              </Space>
            </Card>
          </Col>
        </Row>
      )}

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} lg={12}>
          <Card title="板块1月收益排名">
            {isLoading ? <Spin /> : <ReactECharts option={barOption} style={{ height: 300 }} />}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="板块相对强弱（vs 市场平均）">
            {isLoading ? <Spin /> : <ReactECharts option={rsOption} style={{ height: 300 }} />}
          </Card>
        </Col>
      </Row>

      <Card title="板块详细数据">
        <Table
          dataSource={sectors}
          columns={columns}
          rowKey="category"
          size="small"
          pagination={false}
          loading={isLoading}
        />
      </Card>
    </div>
  );
}
