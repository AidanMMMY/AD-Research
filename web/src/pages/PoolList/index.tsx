import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Button, Modal, Form, Input, message } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useQueryClient } from '@tanstack/react-query';
import { usePoolList } from '@/hooks/usePoolDetail';
import { useDensity } from '@/hooks/useDensity';
import { poolApi } from '@/api';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import FilterToolbar from '@/components/FilterToolbar';
import Panel from '@/components/Panel';

export default function PoolList() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { density } = useDensity();
  const { data: pools } = usePoolList();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [form] = Form.useForm();

  const handleCreate = async (values: { name: string; description?: string }) => {
    try {
      await poolApi.create(values);
      message.success('创建成功');
      setIsModalOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['pools'], exact: false });
    } catch {
      message.error('创建失败');
    }
  };

  const rowSize = density === 'dense' ? 'small' : density === 'spacious' ? 'large' : 'middle';

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
        title="标的池管理"
        description="创建和管理自定义标的池，组织您关注的标的组合"
      />

      <FilterToolbar
        total={`共 ${pools?.length || 0} 个`}
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsModalOpen(true)}>
            新建池
          </Button>
        }
      >
        {null}
      </FilterToolbar>

      <Panel variant="default">
        <Table
          dataSource={pools || []}
          columns={columns}
          rowKey="id"
          size={rowSize as any}
          scroll={{ x: 'max-content' }}
          onRow={(record) => ({
            onClick: () => navigate(`/pools/${record.id}`),
          })}
          pagination={false}
        />
      </Panel>

      <Modal
        title="新建标的池"
        open={isModalOpen}
        onCancel={() => setIsModalOpen(false)}
        onOk={() => form.submit()}
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
