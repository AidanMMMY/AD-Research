import { useParams } from 'react-router-dom';
import { Card, Row, Col, Statistic, Table, Spin } from 'antd';
import { useQuery } from '@tanstack/react-query';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';

export default function BacktestDetail() {
  const { id } = useParams<{ id: string }>();

  const { data, isLoading } = useQuery({
    queryKey: ['backtest', id],
    queryFn: async () => {
      const res = await fetch(`/api/v1/backtests/${id}`);
      return res.json();
    },
  });

  if (isLoading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  if (!data) return <div>回测未找到</div>;

  const metrics = data.metrics || {};

  const navData = data.daily_nav || [];
  const navOption: EChartsOption = {
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 20, top: 30, bottom: 30 },
    xAxis: { type: 'category', data: navData.map((d: any) => d.date) },
    yAxis: { type: 'value' },
    series: [{
      type: 'line',
      data: navData.map((d: any) => d.nav),
      smooth: true,
      areaStyle: { opacity: 0.1 },
    }],
  };

  const tradeColumns = [
    { title: '入场日期', dataIndex: 'entry_date' },
    { title: '出场日期', dataIndex: 'exit_date' },
    { title: '入场价', dataIndex: 'entry_price' },
    { title: '出场价', dataIndex: 'exit_price' },
    {
      title: '收益',
      dataIndex: 'pnl_pct',
      render: (v: number) => <span style={{ color: v >= 0 ? '#cf1322' : '#3f8600' }}>{v}%</span>,
    },
  ];

  return (
    <div>
      <Card title={`回测详情 #${data.id}`} style={{ marginBottom: 16 }}>
        <Row gutter={[16, 16]}>
          <Col xs={12} sm={8}><Card><Statistic title="总收益" value={metrics.total_return} suffix="%" precision={2} /></Card></Col>
          <Col xs={12} sm={8}><Card><Statistic title="年化收益" value={metrics.annualized_return} suffix="%" precision={2} /></Card></Col>
          <Col xs={12} sm={8}><Card><Statistic title="最大回撤" value={metrics.max_drawdown} suffix="%" precision={2} /></Card></Col>
          <Col xs={12} sm={8}><Card><Statistic title="夏普比率" value={metrics.sharpe_ratio} precision={2} /></Card></Col>
          <Col xs={12} sm={8}><Card><Statistic title="胜率" value={metrics.win_rate} suffix="%" precision={2} /></Card></Col>
          <Col xs={12} sm={8}><Card><Statistic title="交易次数" value={metrics.trade_count} /></Card></Col>
        </Row>
      </Card>

      <Card title="净值曲线" style={{ marginBottom: 16 }}>
        <ReactECharts option={navOption} style={{ height: 320 }} />
      </Card>

      <Card title="交易记录">
        <Table
          dataSource={data.trades || []}
          columns={tradeColumns}
          rowKey={(r: any) => `${r.entry_date}-${r.entry_price}`}
          size="small"
          pagination={{ pageSize: 10 }}
        />
      </Card>
    </div>
  );
}
