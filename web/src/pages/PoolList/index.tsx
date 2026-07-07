import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Button, Modal, Form, Input, message } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { usePoolList } from '@/hooks/usePoolDetail';
import { useDensity } from '@/hooks/useDensity';
import { poolApi } from '@/api';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import FilterToolbar from '@/components/FilterToolbar';
import Panel from '@/components/Panel';
import SectionHeading from '@/components/SectionHeading';
import EmptyState from '@/components/EmptyState';

export default function PoolList() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { density } = useDensity();
  const { data: pools, isLoading: poolsLoading } = usePoolList();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [form] = Form.useForm();

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

  const handleCreate = async (values: { name: string; description?: string }) => {
    createMutation.mutate(values);
  };

  const rowSize = density === 'dense' ? 'small' : density === 'spacious' ? 'large' : 'middle';
  const tableWrapClass =
    density === 'dense'
      ? 'ad-density-dense ad-table-scroll ad-table-sticky'
      : 'ad-table-scroll ad-table-sticky';

  const columns = [
    { title: '名称', dataIndex: 'name' },
    { title: '描述', dataIndex: 'description' },
    { title: '成员数', dataIndex: 'members', render: (m: any[]) => m?.length || 0, width: 90 },
    {
      title: '操作',
      width: 120,
      render: (_: unknown, record: any) => (
        <Button type="link" onClick={() => navigate(`/pools/${record.id}`)}>管理</Button>
      ),
    },
  ];

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

      <FilterToolbar total={`共 ${pools?.length || 0} 个`} />

      <SectionHeading title="标的池列表" />

      <Panel variant="default" padding="none">
        <div className={tableWrapClass}>
          <Table
            dataSource={pools || []}
            columns={columns}
            rowKey="id"
            size={rowSize as any}
            scroll={{ x: 'max-content' }}
            loading={poolsLoading}
            onRow={(record) => ({
              onClick: () => navigate(`/pools/${record.id}`),
            })}
            pagination={false}
            locale={{
              emptyText: poolsLoading ? '加载中...' : (
                <div className="ad-p-5">
                  <EmptyState
                    title="暂无标的池"
                    description="点击右上角「新建池」创建第一个标的池"
                    action={
                      <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsModalOpen(true)}>
                        新建池
                      </Button>
                    }
                  />
                </div>
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
