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
import type { ColumnsType } from 'antd/es/table';
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
import { useQueryClient } from '@tanstack/react-query';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import SectionHeading from '@/components/SectionHeading';
import ResponsiveGrid from '@/components/ResponsiveGrid';
import EmptyState from '@/components/EmptyState';
import { useDeployments, useLogStream } from '@/hooks/useDeployments';
import type { DeploymentRun, ContainerStats, LogLine } from '@/types/deployment';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import { formatDateTime, toLocal } from '@/utils/datetime';
dayjs.extend(relativeTime);

const { Text } = Typography;
const { Option } = Select;

// ---------------------------------------------------------------------------
// Deployment history table
// ---------------------------------------------------------------------------

const STATUS_CONFIG: Record<string, { icon: React.ReactNode }> = {
  success: { icon: <CheckCircleOutlined /> },
  failure: { icon: <CloseCircleOutlined /> },
  in_progress: { icon: <SyncOutlined spin /> },
  queued: { icon: <ClockCircleOutlined /> },
};

function formatDuration(seconds: number) {
  if (seconds < 60) return `${seconds}s`;
  const min = Math.floor(seconds / 60);
  const sec = seconds % 60;
  return sec > 0 ? `${min}m ${sec}s` : `${min}m`;
}

function DeploymentsTable({ data, loading }: { data: DeploymentRun[]; loading: boolean }) {
  const columns: ColumnsType<DeploymentRun> = [
    {
      title: '#',
      dataIndex: 'run_number',
      key: 'run_number',
      width: 70,
      fixed: 'left',
      render: (n: number) => <Text className="tabular-nums ad-font-medium">#{n}</Text>,
    },
    {
      title: '状态',
      dataIndex: 'conclusion',
      key: 'status',
      width: 120,
      render: (conclusion: string | null, record: DeploymentRun) => {
        const key = record.status === 'in_progress' ? 'in_progress' : (conclusion || 'unknown');
        const config = STATUS_CONFIG[key] || { icon: null };
        return (
          <Tag
            icon={config.icon}
            className={`admin-deploy-status-tag admin-deploy-status-tag--${key}`}
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
      render: (b: string) => <Text className="ad-text-small">{b}</Text>,
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
            className="font-mono ad-text-small admin-deploy-commit"
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
      render: (s: number) => <Text className="ad-text-small">{formatDuration(s)}</Text>,
    },
    {
      title: '触发',
      dataIndex: 'actor_login',
      key: 'actor',
      width: 100,
      render: (actor: string) => <Text className="ad-text-small">{actor}</Text>,
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created',
      width: 140,
      render: (ts: string) => {
        const d = toLocal(ts);
        return (
          <Tooltip title={formatDateTime(ts, 'YYYY-MM-DD HH:mm:ss')}>
            <Text className="ad-text-small ad-text-secondary">{d.fromNow()}</Text>
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
      scroll={{ x: 'max-content' }}
    />
  );
}

// ---------------------------------------------------------------------------
// Server health cards
// ---------------------------------------------------------------------------

const CONTAINER_COLORS: Record<string, string> = {
  'alloyresearch-backend': 'var(--accent)',
  'alloyresearch-postgres': 'var(--text-secondary)',
  'alloyresearch-redis': 'var(--color-warning)',
  'alloyresearch-nginx': 'var(--color-success)',
};

function ServerHealthCard({ container }: { container: ContainerStats }) {
  const isRunning = container.state === 'running';
  const accentColor = CONTAINER_COLORS[container.name] || 'var(--text-secondary)';
  const memPercent = container.memory_percent || 0;

  return (
    <div
      className={`admin-server-card ${!isRunning ? 'admin-server-card--stopped' : ''}`}
    >
      <div className="admin-server-card__header">
        <Badge status={isRunning ? 'success' : 'error'} />
        <Text strong className="admin-server-card__name">
          {container.name.replace('alloyresearch-', '')}
        </Text>
      </div>

      <Row gutter={[16, 12]}>
        <Col span={12}>
          <Statistic
            title="CPU"
            value={container.cpu_percent}
            suffix="%"
                      />
        </Col>
        <Col span={12}>
          <Statistic
            title="内存"
            value={container.memory_usage.split('/')[0] || '-'}
                      />
        </Col>
      </Row>

      <div className="admin-server-card__progress">
        <Progress
          percent={Math.round(memPercent * 100) / 100}
          size="small"
          strokeColor={accentColor}
          trailColor="var(--bg-input)"
          showInfo={false}
        />
      </div>

      <div className="admin-server-card__footer">
        <Text className="ad-text-small ad-text-secondary">
          运行 {container.uptime}
        </Text>
        <Tooltip title={container.image}>
          <Tag className="admin-server-card__image">
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

const PIN_THRESHOLD_PX = 24; // distance from bottom that still counts as "pinned"

function LogViewer({
  lines,
  connected,
  onConnect,
  onDisconnect,
  onClear,
  container,
  onContainerChange,
}: {
  lines: LogLine[];
  connected: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
  onClear: () => void;
  container: string;
  onContainerChange: (c: string) => void;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  // Apple Design #5 Direct manipulation — respect the user's scroll intent.
  // When the user scrolls up to inspect a line, stop yanking them back down;
  // re-pin only after they return to (or near) the bottom.
  const [pinnedToBottom, setPinnedToBottom] = useState(true);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const distanceFromBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight;
    setPinnedToBottom(distanceFromBottom <= PIN_THRESHOLD_PX);
  }, []);

  useEffect(() => {
    if (!pinnedToBottom) return;
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [lines, pinnedToBottom]);

  return (
    <div>
      <div className="admin-log-section-header">
        <Space>
          <Text strong>实时日志</Text>
          <Badge
            status={connected ? 'processing' : 'default'}
            text={
              <Text className="ad-text-small ad-text-secondary">
                {connected ? '已连接' : '未连接'}
              </Text>
            }
          />
          {!pinnedToBottom && (
            <Text className="ad-text-small ad-text-secondary">
              · 滚动到底部以跟随新日志
            </Text>
          )}
        </Space>
        <Space>
          <Select
            value={container}
            onChange={onContainerChange}
            size="small"
            className="admin-log-container-select"
          >
            <Option value="alloyresearch-backend">backend</Option>
            <Option value="alloyresearch-postgres">postgres</Option>
            <Option value="alloyresearch-redis">redis</Option>
            <Option value="alloyresearch-nginx">nginx</Option>
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
            onClick={onClear}
            aria-label="清除日志"
          />
        </Space>
      </div>

      <div
        ref={scrollRef}
        className="admin-log-terminal"
        onScroll={handleScroll}
      >
        {lines.length === 0 && (
          <div className="admin-log-terminal__empty">
            {connected ? '等待日志 ...' : '点击「连接」开始查看实时日志'}
          </div>
        )}
        {lines.map((line, i) => (
          <div key={i} className="admin-log-line">
            <span className="admin-log-line__timestamp">
              {line.timestamp ? line.timestamp.slice(0, 19).replace('T', ' ') : '-'}
            </span>{' '}
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
  const queryClient = useQueryClient();
  const {
    deployments,
    isLoadingDeployments,
    health,
    isLoadingHealth,
    triggerDeploy,
    isTriggering,
  } = useDeployments();

  const [logContainer, setLogContainer] = useState('alloyresearch-backend');
  const { lines, connected, connect, disconnect, clear: clearLogs } = useLogStream(logContainer);

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

  // Apple Design #1 Response — revalidate React Query caches in place instead
  // of throwing away the whole tree with window.location.reload(). Preserves
  // scroll position, log stream state, and form drafts.
  const handleRefresh = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['deployments'] });
    queryClient.invalidateQueries({ queryKey: ['server-health'] });
  }, [queryClient]);

  const containers = health?.containers || [];

  return (
    <PageShell maxWidth="wide">
      {/* Apple Design overrides scoped to this page (see WWDC "Designing Fluid
          Interfaces"). Layered on top of global.css rules. */}
      <style>{`
        /* #14 Reduced motion — freeze the in-progress spinner instead of an
           endless non-interruptible rotation; a static icon still reads as
           "running" via the tag color/label. */
        @media (prefers-reduced-motion: reduce) {
          .admin-deploy-status-tag--in_progress .anticon-spin {
            animation: none !important;
          }
          .admin-log-terminal { scroll-behavior: auto !important; }
        }
        /* #1 Response — pointer-down feedback on the commit link. */
        .admin-deploy-commit:active {
          opacity: 0.6;
          transition: none;
        }
        /* #15 Typography — tabular figures for the SHA so columns don't jitter
           as logs stream in. */
        .admin-log-line__timestamp { font-variant-numeric: tabular-nums; }
      `}</style>
      <PageHeader
        title="部署管理"
        description="Vercel 风格部署仪表盘 — 查看部署历史、服务器状态和实时日志"
        extra={
          <Space>
            <Button
              icon={<ReloadOutlined />}
              onClick={handleRefresh}
              variant="outlined"
            >
              刷新
            </Button>
            <Button
              type="primary"
              icon={<RocketOutlined />}
              onClick={handleTrigger}
              loading={isTriggering}
            >
              手动部署
            </Button>
          </Space>
        }
      />

      <div className="admin-section">
        <SectionHeading
          title={
            <Space>
              <GithubOutlined />
              <span>部署历史</span>
            </Space>
          }
        />
        <Panel variant="default" padding="md">
          <DeploymentsTable data={deployments} loading={isLoadingDeployments} />
        </Panel>
      </div>

      <div className="admin-section">
        <SectionHeading title="服务器健康" />
        <Panel variant="default" padding="md">
          {containers.length === 0 ? (
            <EmptyState
              title={isLoadingHealth ? '加载中...' : '暂无容器数据'}
              description={isLoadingHealth ? undefined : '需要 Docker socket 访问权限'}
            />
          ) : (
            <ResponsiveGrid cols={4} gap="md">
              {containers.map((c: ContainerStats) => (
                <ServerHealthCard key={c.name} container={c} />
              ))}
            </ResponsiveGrid>
          )}
        </Panel>
      </div>

      <div className="admin-section">
        <SectionHeading title="实时日志" />
        <Panel variant="default" padding="md">
          <LogViewer
            lines={lines}
            connected={connected}
            onConnect={connect}
            onDisconnect={disconnect}
            onClear={clearLogs}
            container={logContainer}
            onContainerChange={handleLogContainerChange}
          />
        </Panel>
      </div>
    </PageShell>
  );
}
