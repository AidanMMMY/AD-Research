import { useState, useEffect, useRef, useCallback } from 'react';
import {
  Table,
  Button,
  Tag,
  Select,
  Space,
  Typography,
  message,
  Tooltip,
  Statistic,
  Row,
  Col,
  Badge,
  Progress,
} from 'antd';
import {
  ReloadOutlined,
  RocketOutlined,
  GithubOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  SyncOutlined,
  ClockCircleOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  ClearOutlined,
} from '@ant-design/icons';
import Panel from '@/components/Panel';
import { useDeployments, useLogStream } from '@/hooks/useDeployments';
import type { DeploymentRun, ContainerStats, LogLine } from '@/types/deployment';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
dayjs.extend(relativeTime);

const { Text } = Typography;
const { Option } = Select;

// ---------------------------------------------------------------------------
// Deployment history table
// ---------------------------------------------------------------------------

const STATUS_CONFIG: Record<string, { color: string; icon: React.ReactNode }> = {
  success: { color: 'var(--accent)', icon: <CheckCircleOutlined /> },
  failure: { color: 'var(--color-error)', icon: <CloseCircleOutlined /> },
  in_progress: { color: 'var(--color-warning)', icon: <SyncOutlined spin /> },
  queued: { color: 'var(--text-secondary)', icon: <ClockCircleOutlined /> },
};

function formatDuration(seconds: number) {
  if (seconds < 60) return `${seconds}s`;
  const min = Math.floor(seconds / 60);
  const sec = seconds % 60;
  return sec > 0 ? `${min}m ${sec}s` : `${min}m`;
}

function DeploymentsTable({ data, loading }: { data: DeploymentRun[]; loading: boolean }) {
  const columns = [
    {
      title: '#',
      dataIndex: 'run_number',
      key: 'run_number',
      width: 70,
      render: (n: number) => <Text style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 500 }}>#{n}</Text>,
    },
    {
      title: '状态',
      dataIndex: 'conclusion',
      key: 'status',
      width: 120,
      render: (conclusion: string | null, record: DeploymentRun) => {
        const key = record.status === 'in_progress' ? 'in_progress' : (conclusion || 'unknown');
        const config = STATUS_CONFIG[key] || { color: 'var(--text-secondary)', icon: null };
        return (
          <Tag
            icon={config.icon}
            style={{
              color: config.color,
              borderColor: config.color,
              background: 'transparent',
              borderRadius: 4,
            }}
          >
            {key === 'in_progress' ? '运行中' : key === 'success' ? '成功' : key === 'failure' ? '失败' : key}
          </Tag>
        );
      },
    },
    {
      title: '分支',
      dataIndex: 'head_branch',
      key: 'branch',
      width: 100,
      render: (b: string) => <Text style={{ fontSize: 13 }}>{b}</Text>,
    },
    {
      title: 'Commit',
      dataIndex: 'head_sha',
      key: 'commit',
      width: 120,
      render: (sha: string, record: DeploymentRun) => (
        <Tooltip title={record.display_title}>
          <a
            href={record.html_url}
            target="_blank"
            rel="noopener noreferrer"
            style={{ fontFamily: 'monospace', fontSize: 13, color: 'var(--accent)' }}
          >
            {sha}
          </a>
        </Tooltip>
      ),
    },
    {
      title: '耗时',
      dataIndex: 'duration_seconds',
      key: 'duration',
      width: 90,
      render: (s: number) => <Text style={{ fontSize: 13 }}>{formatDuration(s)}</Text>,
    },
    {
      title: '触发',
      dataIndex: 'actor_login',
      key: 'actor',
      width: 100,
      render: (actor: string) => <Text style={{ fontSize: 13 }}>{actor}</Text>,
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created',
      width: 140,
      render: (ts: string) => {
        const d = dayjs(ts);
        return (
          <Tooltip title={d.format('YYYY-MM-DD HH:mm:ss')}>
            <Text style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{d.fromNow()}</Text>
          </Tooltip>
        );
      },
    },
  ];

  return (
    <Table
      dataSource={data}
      columns={columns}
      rowKey="id"
      loading={loading}
      size="small"
      pagination={{ pageSize: 10, showSizeChanger: false }}
      locale={{ emptyText: '暂无部署记录（请配置 GITHUB_TOKEN）' }}
      style={{ background: 'transparent' }}
      onRow={() => ({
        style: {
          background: 'transparent',
          borderBottom: '1px solid var(--border-default)',
        },
      })}
    />
  );
}

// ---------------------------------------------------------------------------
// Server health cards
// ---------------------------------------------------------------------------

const CONTAINER_COLORS: Record<string, string> = {
  'etf-backend': 'var(--accent)',
  'etf-postgres': 'var(--text-secondary)',
  'etf-redis': 'var(--color-warning)',
  'etf-nginx': 'var(--color-success)',
};

function ServerHealthCard({ container }: { container: ContainerStats }) {
  const isRunning = container.state === 'running';
  const accentColor = CONTAINER_COLORS[container.name] || 'var(--text-secondary)';
  const memPercent = container.memory_percent || 0;

  return (
    <div
      style={{
        background: 'var(--bg-elevated)',
        borderRadius: 12,
        border: `1px solid ${isRunning ? 'var(--border-default)' : 'var(--color-error)'}`,
        padding: '20px 24px',
        minWidth: 200,
        transition: 'background var(--transition-fast), border-color var(--transition-fast)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
        <Badge status={isRunning ? 'success' : 'error'} />
        <Text strong style={{ color: 'var(--text-primary)', fontSize: 14 }}>
          {container.name.replace('etf-', '')}
        </Text>
      </div>

      <Row gutter={[16, 12]}>
        <Col span={12}>
          <Statistic
            title="CPU"
            value={container.cpu_percent}
            suffix="%"
            valueStyle={{
              fontSize: 20,
              fontWeight: 600,
              color: 'var(--text-primary)',
            }}
          />
        </Col>
        <Col span={12}>
          <Statistic
            title="内存"
            value={container.memory_usage.split('/')[0] || '-'}
            valueStyle={{
              fontSize: 18,
              fontWeight: 500,
              color: 'var(--text-primary)',
            }}
          />
        </Col>
      </Row>

      <div style={{ marginTop: 12 }}>
        <Progress
          percent={Math.round(memPercent * 100) / 100}
          size="small"
          strokeColor={accentColor}
          trailColor="var(--bg-input)"
          showInfo={false}
        />
      </div>

      <div style={{ marginTop: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
          运行 {container.uptime}
        </Text>
        <Tooltip title={container.image}>
          <Tag style={{ fontSize: 11, background: 'var(--bg-input)', border: 'none', color: 'var(--text-secondary)' }}>
            {container.image.split(':')[0]}
          </Tag>
        </Tooltip>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Live log viewer
// ---------------------------------------------------------------------------

function LogViewer({
  lines,
  connected,
  onConnect,
  onDisconnect,
  container,
  onContainerChange,
}: {
  lines: LogLine[];
  connected: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
  container: string;
  onContainerChange: (c: string) => void;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [lines]);

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 12,
          gap: 12,
          flexWrap: 'wrap',
        }}
      >
        <Space>
          <Text strong style={{ color: 'var(--text-primary)', fontSize: 14 }}>实时日志</Text>
          <Badge
            status={connected ? 'processing' : 'default'}
            text={
              <Text style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                {connected ? '已连接' : '未连接'}
              </Text>
            }
          />
        </Space>
        <Space>
          <Select
            value={container}
            onChange={onContainerChange}
            size="small"
            style={{ width: 130 }}
          >
            <Option value="etf-backend">backend</Option>
            <Option value="etf-postgres">postgres</Option>
            <Option value="etf-redis">redis</Option>
            <Option value="etf-nginx">nginx</Option>
          </Select>
          <Button
            size="small"
            icon={connected ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
            onClick={connected ? onDisconnect : onConnect}
          >
            {connected ? '断开' : '连接'}
          </Button>
          <Button
            size="small"
            icon={<ClearOutlined />}
            onClick={() => {
              onDisconnect();
              if (scrollRef.current) scrollRef.current.innerHTML = '';
            }}
          />
        </Space>
      </div>

      <div
        ref={scrollRef}
        style={{
          background: '#0a0e17',
          border: '1px solid var(--border-default)',
          borderRadius: 8,
          height: 360,
          overflow: 'auto',
          padding: '12px 16px',
          fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
          fontSize: 12,
          lineHeight: '1.8',
          color: '#a8b8c8',
        }}
      >
        {lines.length === 0 && (
          <div style={{ color: 'var(--text-secondary)', padding: '40px 0', textAlign: 'center' }}>
            {connected ? '等待日志 ...' : '点击「连接」开始查看实时日志'}
          </div>
        )}
        {lines.map((line, i) => (
          <div key={i} style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
            <span style={{ color: '#5a6a7a' }}>{line.timestamp ? line.timestamp.slice(0, 19).replace('T', ' ') : '-'}</span>{' '}
            {line.message}
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export default function AdminDeployments() {
  const {
    deployments,
    isLoadingDeployments,
    health,
    isLoadingHealth,
    triggerDeploy,
    isTriggering,
  } = useDeployments();

  const [logContainer, setLogContainer] = useState('etf-backend');
  const { lines, connected, connect, disconnect } = useLogStream(logContainer);

  const handleLogContainerChange = useCallback(
    (c: string) => {
      disconnect();
      setLogContainer(c);
    },
    [disconnect]
  );

  const handleTrigger = async () => {
    try {
      await triggerDeploy();
      message.success('部署已触发，请关注部署历史');
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '触发失败');
    }
  };

  const containers = health?.containers || [];

  return (
    <div style={{ maxWidth: 1200 }}>
      {/* Page header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 28,
          flexWrap: 'wrap',
          gap: 12,
        }}
      >
        <div>
          <Text style={{ fontSize: 24, fontWeight: 600, color: 'var(--text-primary)' }}>
            部署管理
          </Text>
          <Text style={{ display: 'block', fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
            Vercel 风格部署仪表盘 — 查看部署历史、服务器状态和实时日志
          </Text>
        </div>
        <Space>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => {
              window.location.reload();
            }}
            variant="outlined"
          >
            刷新
          </Button>
          <Button
            type="primary"
            icon={<RocketOutlined />}
            onClick={handleTrigger}
            loading={isTriggering}
            style={{ background: 'var(--accent)', borderColor: 'var(--accent)', color: '#000' }}
          >
            手动部署
          </Button>
        </Space>
      </div>

      {/* --- Deployment History --- */}
      <Panel
        title={
          <Space>
            <GithubOutlined />
            <span>部署历史</span>
          </Space>
        }
        extra={
          <Text style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
            来自 GitHub Actions
          </Text>
        }
        variant="minimal"
        style={{ marginBottom: 28 }}
      >
        <DeploymentsTable data={deployments} loading={isLoadingDeployments} />
      </Panel>

      {/* --- Server Health --- */}
      <Panel
        title="服务器健康"
        variant="minimal"
        style={{ marginBottom: 28 }}
      >
        {containers.length === 0 ? (
          <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-secondary)' }}>
            {isLoadingHealth ? '加载中...' : '暂无容器数据（需要 Docker socket 访问权限）'}
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16 }}>
            {containers.map((c: ContainerStats) => (
              <ServerHealthCard key={c.name} container={c} />
            ))}
          </div>
        )}
      </Panel>

      {/* --- Live Logs --- */}
      <Panel title="实时日志" variant="minimal">
        <LogViewer
          lines={lines}
          connected={connected}
          onConnect={connect}
          onDisconnect={disconnect}
          container={logContainer}
          onContainerChange={handleLogContainerChange}
        />
      </Panel>
    </div>
  );
}
