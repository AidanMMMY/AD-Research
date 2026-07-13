import type { CSSProperties } from 'react';
import { Descriptions, Modal, Space, Tag } from 'antd';
import { FileTextOutlined, InboxOutlined } from '@ant-design/icons';
import EmptyState from '@/components/EmptyState';
import type { ListingEventDetail, ListingStatus } from '@/types/listingEvent';
import { STATUS_LABEL } from '@/types/listingEvent';
import { useIsMobile } from '@/hooks/useBreakpoint';

interface DetailModalProps {
  open: boolean;
  loading: boolean;
  event: ListingEventDetail | null | undefined;
  onClose: () => void;
  /** Viewport coordinates of the row that opened the modal — the
   *  modal scales out from this point per Apple "Spatial consistency"
   *  (transform-origin anchored to the trigger). */
  anchor?: { x: number; y: number } | null;
}

const STATUS_COLOR: Record<ListingStatus, string> = {
  upcoming: 'blue',
  subscribing: 'orange',
  listed: 'green',
  unknown: 'default',
};

const formatNumber = (v: number | null | undefined, suffix?: string): string => {
  if (v === null || v === undefined) return '-';
  return `${v.toLocaleString('zh-CN', { maximumFractionDigits: 4 })}${suffix ?? ''}`;
};

const formatYuan = (v: number | null | undefined): string => {
  if (v === null || v === undefined) return '-';
  // funds_raised is in 万元 (10K CNY); display in 亿元 for readability
  return `${(v / 1e4).toFixed(2)} 亿元`;
};

const formatDate = (v: string | null | undefined): string => v ?? '-';

export default function ListingEventDetailModal({
  open,
  loading,
  event,
  onClose,
  anchor,
}: DetailModalProps) {
  const isMobile = useIsMobile();
  // ``anchor`` carries the row's viewport position; we forward it as
  // CSS variables on the modal wrap so the entrance keyframes scale
  // out from the row instead of from screen center.
  const wrapStyle: CSSProperties = anchor
    ? ({
        ['--listing-modal-origin-x' as string]: `${anchor.x}px`,
        ['--listing-modal-origin-y' as string]: `${anchor.y}px`,
      } as CSSProperties)
    : {};
  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width={isMobile ? '100%' : 720}
      destroyOnClose
      className="listing-preview-detail-modal"
      wrapClassName="listing-preview-detail-modal-wrap"
      style={wrapStyle}
      title={
        event ? (
          <Space>
            <strong>{event.name}</strong>
            <Tag color={STATUS_COLOR[event.status]}>{STATUS_LABEL[event.status]}</Tag>
            <span className="last-updated tabular-nums">{event.ts_code}</span>
          </Space>
        ) : (
          '上市预告详情'
        )
      }
    >
      {loading ? (
        <EmptyState
          icon={<FileTextOutlined />}
          title="加载中..."
          description="正在获取上市预告详情"
        />
      ) : event ? (
        <Descriptions
          bordered
          size="small"
          column={{ xs: 1, sm: 2, md: 2 }}
          rootClassName="tabular-nums"
        >
          <Descriptions.Item label="证券代码">{event.ts_code}</Descriptions.Item>
          <Descriptions.Item label="申购代码">{event.sub_code ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="证券简称">{event.name}</Descriptions.Item>
          <Descriptions.Item label="交易所">{event.market ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="板块">{event.board ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="行业">{event.industry ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="发行日期">{formatDate(event.issue_date)}</Descriptions.Item>
          <Descriptions.Item label="上市日期">{formatDate(event.list_date)}</Descriptions.Item>
          <Descriptions.Item label="发行价 (元)">{formatNumber(event.issue_price)}</Descriptions.Item>
          <Descriptions.Item label="发行市盈率">{formatNumber(event.pe_ratio)}</Descriptions.Item>
          <Descriptions.Item label="申购上限 (万元)">{formatNumber(event.limit_amount)}</Descriptions.Item>
          <Descriptions.Item label="募集资金">{formatYuan(event.funds_raised)}</Descriptions.Item>
          <Descriptions.Item label="发行后总股本 (万股)">{formatNumber(event.market_amount)}</Descriptions.Item>
          <Descriptions.Item label="保荐机构" span={2}>{event.sponsor ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="承销商" span={2}>{event.underwriter ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="数据来源">{event.source}</Descriptions.Item>
          <Descriptions.Item label="更新时间">{event.updated_at ?? '-'}</Descriptions.Item>
        </Descriptions>
      ) : (
        <EmptyState
          icon={<InboxOutlined />}
          title="未找到记录"
        />
      )}
    </Modal>
  );
}
