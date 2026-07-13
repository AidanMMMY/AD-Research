import './styles.css';

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Button, Modal, Form, Input, message, Popconfirm, Space } from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { usePoolList } from '@/hooks/usePoolDetail';
import { poolApi } from '@/api';
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import FilterToolbar from '@/components/FilterToolbar';
import Panel from '@/components/Panel';
import EmptyState from '@/components/EmptyState';

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

  const tableWrapClass = 'ad-table-scroll ad-table-sticky';

  const columns = [
    { title: '名称', dataIndex: 'name' },
    { title: '描述', dataIndex: 'description' },
    { title: '成员数', dataIndex: 'members', render: (m: any[]) => m?.length || 0, width: 90 },
    {
      title: '操作',
      width: 160,
      render: (_: unknown, record: any) => (
        <Space onClick={(e) => e.stopPropagation()}>
          <Button type="link" onClick={() => navigate(`/pools/${record.id}`)}>管理</Button>
          <Popconfirm
            title="删除标的池"
            description={`确定要删除「${record.name}」吗？此操作不可恢复。`}
            onConfirm={() => deleteMutation.mutate(record.id)}
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true, loading: deleteMutation.isPending && deleteMutation.variables === record.id }}
          >
            <Button type="link" danger icon={<DeleteOutlined />} loading={deleteMutation.isPending && deleteMutation.variables === record.id}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <PageShell maxWidth="wide">
      {/* Apple Design #1 Response / #10 Gesture details: clickable rows give
          instant pointer-down feedback (tap-highlight equivalent). Background
          only — no movement, so no reduced-motion concern. */}
      <style>{`
        .pool-list-row--pressable > td { transition: background var(--transition-fast, 150ms ease); }
        .pool-list-row--pressable:active > td { background: var(--bg-active) !important; }
      `}</style>
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

      <Panel variant="default" padding="md">
        <FilterToolbar total={`共 ${pools?.length || 0} 个`} />

        <div className={tableWrapClass}>
          <Table
            dataSource={pools || []}
            columns={columns}
            rowKey="id"
            size="small"
            rowClassName="pool-list-row--pressable"
            scroll={{ x: 'max-content' }}
            loading={poolsLoading}
            onRow={(record) => ({
              onClick: () => navigate(`/pools/${record.id}`),
              // Apple Design #10 Agency: clickable rows must be operable by
              // keyboard — tab to focus, Enter/Space to activate.
              tabIndex: 0,
              role: 'link',
              onKeyDown: (e: React.KeyboardEvent<HTMLElement>) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  navigate(`/pools/${record.id}`);
                }
              },
            })}
            pagination={false}
            locale={{
              emptyText: poolsLoading ? '加载中...' : (
                <EmptyState
                  title="暂无标的池"
                  description="点击右上角「新建池」创建第一个标的池"
                  action={
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsModalOpen(true)}>
                      新建池
                    </Button>
                  }
                />
              ),
            }}
          />
        </div>
      </Panel>

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
