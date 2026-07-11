import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Table,
  Button,
  Popconfirm,
  Tooltip,
  Empty,
  Collapse,
  Space,
  Tag,
} from 'antd';
import {
  StarFilled,
  DeleteOutlined,
  ReloadOutlined,
  PlusOutlined,
  BulbOutlined,
} from '@ant-design/icons';
import { useQueryClient } from '@tanstack/react-query';
import { useFavorites } from '@/hooks/useFavorites';
import { useMarketStream, type MarketTick } from '@/hooks/useMarketStream';
import { favoriteApi } from '@/api/favorite';
import './styles.css';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import EmptyState from '@/components/EmptyState';
import LoadingBlock from '@/components/LoadingBlock';
import SectionHeading from '@/components/SectionHeading';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import ThemeTag from '@/components/ThemeTag';
import ReturnTag from '@/components/ReturnTag';
import FavoriteToggleButton from '@/components/FavoriteToggleButton';
import { formatDateTime, formatDateTimeCompact } from '@/utils/datetime';
import { NULL_PLACEHOLDER } from '@/utils/format';
import { getReturnColor } from '@/utils/color';

/**
 * 我的自选股页面
 *
 * 功能：
 *   1. 列表展示当前用户已收藏的标的（代码 / 名称 / 分类 / 市场 / 实时价 / 涨跌幅 / 添加时间 / 移除）
 *   2. 按分类自动分组（折叠展示）
 *   3. 实时价通过 useMarketStream 复用 SSE 连接
 *   4. 支持单条移除 + 批量移除
 *   5. 空状态引导：提示用户在标的详情页 / 列表页点星标即可加入自选
 *
 * 数据模型来自后端 ``app/models/favorite.py::UserFavorite``，
 * 业务逻辑 ``app/services/favorite_service.py``，
 * API 端点 ``/api/v1/favorites`` （需鉴权）。
 */
export default function Favorites() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [removing, setRemoving] = useState<string | null>(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [bulkRemoving, setBulkRemoving] = useState(false);

  // 拉全量自选股（按加入时间倒序），上限 200 条
  const { favorites, count, isLoading } = useFavorites(200);

  // 实时价：复用全应用唯一的 SSE 连接
  const codes = useMemo(
    () => favorites.map((f: any) => f.etf_code).filter(Boolean),
    [favorites]
  );
  const { latest: liveLatest, isConnected } = useMarketStream(codes);

  // SSE 返回的 code 会被后端归一化（如 510300.SH），而收藏记录里存的是
  // 用户原始 code（如 510300）。这里把两种 key 都映射到 base code，保证
  // 任意一种格式都能命中实时 tick。
  const liveTickByBaseCode = useMemo(() => {
    const map: Record<string, MarketTick> = {};
    for (const [key, tick] of Object.entries(liveLatest)) {
      if (!tick) continue;
      map[key] = tick;
      const base = key.replace(/\.(SH|SZ|BJ|SS)$/i, '');
      if (base !== key) {
        map[base] = tick;
      }
    }
    return map;
  }, [liveLatest]);

  const getLiveTick = (code: string): MarketTick | undefined =>
    liveTickByBaseCode[code] ?? liveTickByBaseCode[code.replace(/\.(SH|SZ|BJ|SS)$/i, '')];

  /**
   * 移除单条：调 DELETE /api/v1/favorites/{code}，然后让 React Query
   * 失效列表缓存，实现「删除即更新」。这里走 favoriteApi.remove() 而不是
   * hook 里的 toggle，避免 toggle 二次请求 status。
   */
  const handleRemove = async (code: string) => {
    setRemoving(code);
    try {
      await favoriteApi.remove(code).then((r) => r.data);
      queryClient.invalidateQueries({ queryKey: ['favorites'] });
      queryClient.invalidateQueries({ queryKey: ['favorite-status', code] });
    } catch {
      /* swallow — UI 会通过 invalidate 重新拉数据自洽 */
    } finally {
      setRemoving(null);
    }
  };

  /**
   * 批量移除：用 Promise.all 并发删，逐条失效缓存。
   */
  const handleBulkRemove = async () => {
    if (selectedRowKeys.length === 0) return;
    setBulkRemoving(true);
    try {
      await Promise.all(
        selectedRowKeys.map((key) =>
          favoriteApi.remove(String(key)).then((r) => r.data).catch(() => null)
        )
      );
      setSelectedRowKeys([]);
      queryClient.invalidateQueries({ queryKey: ['favorites'] });
    } finally {
      setBulkRemoving(false);
    }
  };

  /**
   * 按分类分组，便于在长列表里快速定位。
   * 未分类的归入「未分类」组。
   */
  const grouped = useMemo(() => {
    const map = new Map<string, any[]>();
    for (const f of favorites) {
      const key = f.category || '未分类';
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(f);
    }
    return Array.from(map.entries()).map(([cat, items]) => ({
      category: cat,
      items,
    }));
  }, [favorites]);

  /** 表格列定义（每行一个自选股） */
  const columns = [
    {
      title: '标的',
      key: 'code',
      width: 220,
      render: (_: unknown, record: any) => (
        <InstrumentCodeTag
          code={record.etf_code}
          name={record.etf_name}
        />
      ),
    },
    {
      title: '分类',
      dataIndex: 'category',
      width: 120,
      render: (v?: string) => (v ? <ThemeTag>{v}</ThemeTag> : <span className="ad-text-muted">{NULL_PLACEHOLDER}</span>),
    },
    {
      title: '市场',
      dataIndex: 'market',
      width: 90,
      render: (v?: string) => (
        <span className="tabular-nums font-mono ad-text-muted">{v || NULL_PLACEHOLDER}</span>
      ),
    },
    {
      title: '当前价',
      key: 'price',
      width: 110,
      align: 'right' as const,
      render: (_: unknown, record: any) => {
        const tick = getLiveTick(record.etf_code);
        if (!tick) {
          return <span className="tabular-nums ad-text-muted">{NULL_PLACEHOLDER}</span>;
        }
        return (
          <span
            className="tabular-nums live-price-cell__price"
            style={{ color: getReturnColor(tick.change_pct) }}
          >
            {tick.price.toFixed(2)}
          </span>
        );
      },
    },
    {
      title: '涨跌幅',
      key: 'change',
      width: 100,
      align: 'right' as const,
      render: (_: unknown, record: any) => {
        const tick = getLiveTick(record.etf_code);
        if (!tick || tick.change_pct == null) {
          return <span className="ad-text-muted">{NULL_PLACEHOLDER}</span>;
        }
        return <ReturnTag value={tick.change_pct} />;
      },
    },
    {
      title: '添加时间',
      key: 'added',
      width: 170,
      render: (_: unknown, record: any) =>
        record.created_at ? (
          <Tooltip title={formatDateTime(record.created_at, 'YYYY-MM-DD HH:mm:ss')}>
            <span className="tabular-nums ad-text-muted">
              {formatDateTimeCompact(record.created_at)}
            </span>
          </Tooltip>
        ) : (
          <span className="ad-text-muted">{NULL_PLACEHOLDER}</span>
        ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 110,
      fixed: 'right' as const,
      render: (_: unknown, record: any) => (
        <Space size="small">
          <Tooltip title="查看详情">
            <Button
              size="small"
              type="link"
              onClick={() => navigate(`/instruments/${record.etf_code}`)}
            >
              详情
            </Button>
          </Tooltip>
          <Popconfirm
            title="确认移除自选？"
            description={`将从自选股中移除 ${record.etf_name || record.etf_code}`}
            okText="移除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            onConfirm={() => handleRemove(record.etf_code)}
          >
            <Button
              size="small"
              type="link"
              danger
              loading={removing === record.etf_code}
              icon={<DeleteOutlined />}
            >
              移除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  /** 单分类表格（用于折叠面板内） */
  const renderGroupTable = (items: any[]) => (
    <Table
      dataSource={items}
      columns={columns}
      rowKey="etf_code"
      size="middle"
      pagination={false}
      scroll={{ x: 720 }}
      onRow={(record: any) => ({
        onClick: () => navigate(`/instruments/${record.etf_code}`),
        style: { cursor: 'pointer' },
      })}
    />
  );

  // ─────────────────────────────────────────────────────────────
  // 加载中
  // ─────────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <PageShell maxWidth="wide">
        <PageHeader
          eyebrow="研究工具"
          title="我的自选股"
          description="管理你关注的标的，用于快速跟踪行情、收益和相关新闻。"
        />
        <Panel variant="default" padding="lg">
          <LoadingBlock size="lg" label="正在加载自选股…" />
        </Panel>
      </PageShell>
    );
  }

  // ─────────────────────────────────────────────────────────────
  // 空状态：引导用户如何添加
  // ─────────────────────────────────────────────────────────────
  if (count === 0) {
    return (
      <PageShell maxWidth="wide">
        <PageHeader
          eyebrow="研究工具"
          title="我的自选股"
          description="管理你关注的标的，用于快速跟踪行情、收益和相关新闻。"
        />
        <Panel variant="default" padding="lg">
          <EmptyState
            icon={<StarFilled className="ad-icon-accent fav-empty-icon" />}
            title="还没有自选股"
            description="在标的详情页或评分榜单中点击 ★ 即可加入自选。这里会汇总你的关注列表，并自动跟踪实时行情与相关新闻。"
            action={
              <Space size="middle" wrap>
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={() => navigate('/instruments')}
                >
                  去标的列表添加
                </Button>
                <Button
                  icon={<BulbOutlined />}
                  onClick={() => navigate('/screen')}
                >
                  用筛选器发现
                </Button>
                <Button onClick={() => navigate('/scores')}>
                  查看评分榜单
                </Button>
              </Space>
            }
          />
        </Panel>
      </PageShell>
    );
  }

  // ─────────────────────────────────────────────────────────────
  // 正常列表
  // ─────────────────────────────────────────────────────────────
  return (
    <PageShell maxWidth="wide">
      <PageHeader
        eyebrow="研究工具"
        title={
          <span>
            <StarFilled className="ad-icon-accent" /> 我的自选股
          </span>
        }
        description={`共 ${count} 只标的，按加入时间倒序排列。${isConnected ? '实时行情已连接' : '实时行情连接中…'}`}
        extra={
          <Space>
            {selectedRowKeys.length > 0 && (
              <Popconfirm
                title={`确认移除选中的 ${selectedRowKeys.length} 只标的？`}
                okText="批量移除"
                cancelText="取消"
                okButtonProps={{ danger: true }}
                onConfirm={handleBulkRemove}
              >
                <Button
                  danger
                  icon={<DeleteOutlined />}
                  loading={bulkRemoving}
                >
                  批量移除 ({selectedRowKeys.length})
                </Button>
              </Popconfirm>
            )}
            <Button
              icon={<ReloadOutlined />}
              onClick={() => queryClient.invalidateQueries({ queryKey: ['favorites'] })}
            >
              刷新
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => navigate('/instruments')}
            >
              添加更多
            </Button>
          </Space>
        }
      />

      {/* 全部标的表（支持批量选择 / 单条移除） */}
      <SectionHeading
        title="全部自选股"
        action={
          <span className="ad-text-muted favorites__hint-text">
            点击行进入详情；勾选后可批量移除
          </span>
        }
      />
      <Panel variant="default" padding="none">
        <Table
          dataSource={favorites}
          columns={columns}
          rowKey="etf_code"
          size="middle"
          pagination={{ pageSize: 20, showSizeChanger: false }}
          scroll={{ x: 720 }}
          rowSelection={{
            selectedRowKeys,
            onChange: (keys) => setSelectedRowKeys(keys),
            preserveSelectedRowKeys: true,
          }}
          onRow={(record: any) => ({
            onClick: (e) => {
              // 选中复选框 / 操作列时不要跳转
              const target = e.target as HTMLElement;
              if (
                target.closest('.ant-checkbox-wrapper') ||
                target.closest('button') ||
                target.closest('a')
              ) {
                return;
              }
              navigate(`/instruments/${record.etf_code}`);
            },
            style: { cursor: 'pointer' },
          })}
        />
      </Panel>

      {/* 按分类分组（折叠面板） */}
      {grouped.length > 1 && (
        <>
          <SectionHeading
            title="按分类浏览"
            action={
              <span className="ad-text-muted favorites__hint-text">
                展开分类查看分组内标的
              </span>
            }
          />
          <Panel variant="default" padding="md">
            <Collapse
              ghost
              items={grouped.map((g) => ({
                key: g.category,
                label: (
                  <Space>
                    <Tag color="blue">{g.category}</Tag>
                    <span className="ad-text-muted">{g.items.length} 只</span>
                  </Space>
                ),
                children: renderGroupTable(g.items),
              }))}
            />
          </Panel>
        </>
      )}

      {/* 已移除标的提示横幅（占位：保持与 Dashboard 风格一致） */}
      <Panel variant="default" padding="md" className="ad-mt-5">
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={
            <span className="ad-text-muted">
              自选股是 <b>轻量级跟踪清单</b>，区别于「标的池」（中长期目标组合）和「模拟 / 真实交易」中的实际持仓。
              如需给自选股配置权重 / 算法跟踪，请到 <a onClick={() => navigate('/pools')}>标的池管理</a>。
            </span>
          }
        />
      </Panel>

      {/* 收藏开关的隐藏语义元素：在每个分类面板标题栏内嵌一颗星，便于将来扩展 */}
      <div className="favorites__hidden-util" aria-hidden>
        <FavoriteToggleButton code="" />
      </div>
    </PageShell>
  );
}