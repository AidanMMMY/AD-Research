import { useParams } from 'react-router-dom';
import { Row, Col, Statistic, Table, Spin } from 'antd';
import GlassCard from '@/components/GlassCard';
import HelpTrigger from '@/components/HelpTrigger';
import HelpPopover from '@/components/HelpPopover';
import { useBacktestDetail } from '@/hooks/useBacktests';
import { useAIHelp } from '@/hooks/useAIHelp';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { useIsMobile } from '@/hooks/useBreakpoint';
import { buildBacktestDetailContext } from '@/utils/helpContext';
import { getQuickQuestions } from '@/utils/helpPrompts';

export default function BacktestDetail() {
  const { id } = useParams<{ id: string }>();
  const { data, isLoading } = useBacktestDetail(id || '');
  const { open } = useAIHelp();
  const isMobile = useIsMobile();

  if (isLoading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  if (!data) return <div>回测未找到</div>;

  const metrics = data.metrics || {};

  const handleOpenHelp = () => {
    open({
      pageType: 'backtest_detail',
      pageTitle: '回测详情',
      contextData: buildBacktestDetailContext(data),
      quickQuestions: getQuickQuestions('backtest_detail'),
    });
  };

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
      render: (v: number) => <span style={{ color: v >= 0 ? '#ef4444' : '#22c55e' }}>{v}%</span>,
    },
  ];

  return (
    <div>
      <GlassCard
        title={`回测详情 #${data.id}`}
        style={{ marginBottom: 16 }}
        extra={<HelpTrigger tooltip="AI 解释回测指标" onClick={handleOpenHelp} />}
      >
        <Row gutter={[16, 16]}>
          <Col xs={12} sm={8}><GlassCard padding="sm"><Statistic title={<HelpPopover termKey="total_return">总收益</HelpPopover>} value={metrics.total_return} suffix="%" precision={2} /></GlassCard></Col>
          <Col xs={12} sm={8}><GlassCard padding="sm"><Statistic title={<HelpPopover termKey="annualized_return">年化收益</HelpPopover>} value={metrics.annualized_return} suffix="%" precision={2} /></GlassCard></Col>
          <Col xs={12} sm={8}><GlassCard padding="sm"><Statistic title={<HelpPopover termKey="max_drawdown_1y">最大回撤</HelpPopover>} value={metrics.max_drawdown} suffix="%" precision={2} /></GlassCard></Col>
          <Col xs={12} sm={8}><GlassCard padding="sm"><Statistic title={<HelpPopover termKey="sharpe_ratio">夏普比率</HelpPopover>} value={metrics.sharpe_ratio} precision={2} /></GlassCard></Col>
          <Col xs={12} sm={8}><GlassCard padding="sm"><Statistic title={<HelpPopover termKey="win_rate">胜率</HelpPopover>} value={metrics.win_rate} suffix="%" precision={2} /></GlassCard></Col>
          <Col xs={12} sm={8}><GlassCard padding="sm"><Statistic title={<HelpPopover termKey="trade_count">交易次数</HelpPopover>} value={metrics.trade_count} /></GlassCard></Col>
        </Row>
      </GlassCard>

      <GlassCard title={<HelpPopover termKey="nav_curve">净值曲线</HelpPopover>} style={{ marginBottom: 16 }}>
        <ReactECharts option={navOption} style={{ height: isMobile ? 250 : 320 }} />
      </GlassCard>

      <GlassCard title={<HelpPopover termKey="trade_record">交易记录</HelpPopover>} style={{ marginBottom: 16 }}>
        <Table
          dataSource={data.trades || []}
          columns={tradeColumns}
          rowKey={(r: any) => `${r.entry_date}-${r.entry_price}`}
          size="small"
          scroll={{ x: 'max-content' }}
          pagination={{ pageSize: 10 }}
        />
      </GlassCard>
    </div>
  );
}
