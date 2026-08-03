import React from 'react';
import { Button } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import EmptyState from './EmptyState';

export interface ErrorStateProps {
  /** 标题，默认「加载失败」 */
  title?: React.ReactNode;
  /** 描述，默认通用文案；可传入具体错误信息 */
  description?: React.ReactNode;
  /** 重试回调（通常传 query.refetch）；不传则不渲染重试按钮 */
  onRetry?: () => void;
  /** 重试进行中（通常传 query.isFetching / isRefetching） */
  retrying?: boolean;
  className?: string;
  style?: React.CSSProperties;
}

/**
 * 错误态 EmptyState 变体 — 核心原则：错误不能伪装成空态。
 *
 * 查询失败时应渲染本组件（带重试出口），而不是落入「暂无数据」分支，
 * 避免用户把接口故障误读为真的没有数据。
 */
export default function ErrorState({
  title = '加载失败',
  description = '数据加载失败，请稍后重试',
  onRetry,
  retrying = false,
  className,
  style,
}: ErrorStateProps) {
  return (
    <EmptyState
      className={className}
      style={style}
      title={title}
      description={description}
      action={
        onRetry ? (
          <Button
            icon={<ReloadOutlined />}
            loading={retrying}
            onClick={onRetry}
          >
            重试
          </Button>
        ) : undefined
      }
    />
  );
}
