import './styles.css';

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Modal, Form, Input, message, Popconfirm, Spin, Tooltip } from 'antd';
import { PlusOutlined, SettingOutlined, DeleteOutlined } from '@ant-design/icons';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { usePoolList } from '@/hooks/usePoolDetail';
import { poolApi } from '@/api';
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import FilterToolbar from '@/components/FilterToolbar';
import ResponsiveGrid from '@/components/ResponsiveGrid';
import EmptyState from '@/components/EmptyState';
import { formatDate } from '@/utils/format';
import type { Pool } from '@/types/pool';

export default function PoolList() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: pools, isLoading: poolsLoading } = usePoolList();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [form] = Form.useForm();
  // Apple Design #14: under reduced motion, drop the modal's spring/zoom
  // keyframe so the overlay cross-fades (or appears instantly) instead.
  const reducedMotion = usePrefersReducedMotion();
  const modalMotionProps = reducedMotion
    ? { transitionName: '', maskTransitionName: '' }
    : {};

  const createMutation = useMutation({
    mutationFn: (values: { name: string; description?: string }) => poolApi.create(values),
    onSuccess: () => {
      message.success('创建成功');
      setIsModalOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['pools'], exact: false });
    },
    onError: () => {
      message.error('创建失败');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => poolApi.delete(id),
    onSuccess: () => {
      message.success('删除成功');
      queryClient.invalidateQueries({ queryKey: ['pools'], exact: false });
    },
    onError: (error: any) => {
      message.error(error?.response?.data?.detail || '删除失败');
    },
  });

  const handleCreate = async (values: { name: string; description?: string }) => {
    createMutation.mutate(values);
  };

  // Cards are whole-surface links; keyboard activation mirrors the row
  // pattern used on the old table (Enter/Space).
  const openPool = (id: number) => navigate(`/pools/${id}`);
  const handleCardKeyDown = (e: React.KeyboardEvent<HTMLElement>, id: number) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      openPool(id);
    }
  };

  const renderCard = (pool: Pool) => (
    <div
      key={pool.id}
      className="pool-card"
      role="link"
      tabIndex={0}
      onClick={() => openPool(pool.id)}
      onKeyDown={(e) => handleCardKeyDown(e, pool.id)}
    >
      <div className="pool-card__header">
        <span className="pool-card__name">{pool.name}</span>
        <span className="tabular-nums pool-card__count">{pool.members?.length || 0} 只</span>
      </div>
      <p className="pool-card__desc">{pool.description || '暂无描述'}</p>
      <div className="pool-card__footer">
        <span className="pool-card__date">创建于 {formatDate(pool.created_at)}</span>
        {/* Action icon-buttons must not trigger card navigation — stop both
            click and keydown from bubbling to the card's handlers. */}
        <span className="pool-card__actions">
          <Tooltip title="管理">
            <Button
              type="text"
              size="small"
              icon={<SettingOutlined />}
              aria-label={`管理 ${pool.name}`}
              onClick={(e) => {
                e.stopPropagation();
                openPool(pool.id);
              }}
              onKeyDown={(e) => e.stopPropagation()}
            />
          </Tooltip>
          <Popconfirm
            title="删除标的池"
            description={`确定要删除「${pool.name}」吗？此操作不可恢复。`}
            onConfirm={() => deleteMutation.mutate(pool.id)}
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true, loading: deleteMutation.isPending && deleteMutation.variables === pool.id }}
          >
            <Tooltip title="删除">
              <Button
                type="text"
                size="small"
                danger
                icon={<DeleteOutlined />}
                aria-label={`删除 ${pool.name}`}
                loading={deleteMutation.isPending && deleteMutation.variables === pool.id}
                onClick={(e) => e.stopPropagation()}
                onKeyDown={(e) => e.stopPropagation()}
              />
            </Tooltip>
          </Popconfirm>
        </span>
      </div>
    </div>
  );

  return (
    <PageShell maxWidth="wide">
      <PageHeader
        eyebrow="组合"
        title="标的池管理"
        description="管理关注池与研究篮子，用于分组跟踪标的。注：标的池是关注列表，不是实际持仓——实际持仓请到「模拟交易」或「真实交易」页面查看。"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsModalOpen(true)}>
            新建池
          </Button>
        }
      />

      <FilterToolbar total={`共 ${pools?.length || 0} 个`} className="ad-mb-4" />

      {poolsLoading ? (
        <div className="pool-list-loading">
          <Spin />
        </div>
      ) : (pools?.length ?? 0) === 0 ? (
        <EmptyState
          title="暂无标的池"
          description="点击右上角「新建池」创建第一个标的池"
          action={
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsModalOpen(true)}>
              新建池
            </Button>
          }
        />
      ) : (
        <ResponsiveGrid cols={3} gap="md" stretch>
          {(pools || []).map(renderCard)}
        </ResponsiveGrid>
      )}

      <Modal
        title="新建标的池"
        open={isModalOpen}
        onCancel={() => setIsModalOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={createMutation.isPending}
        {...modalMotionProps}
      >
        <Form form={form} onFinish={handleCreate} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea />
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}
