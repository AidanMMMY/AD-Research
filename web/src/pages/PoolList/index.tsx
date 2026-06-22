import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Button, Modal, Form, Input, message } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useQueryClient } from '@tanstack/react-query';
import { usePoolList } from '@/hooks/usePoolDetail';
import { poolApi } from '@/api';
import GlassCard from '@/components/GlassCard';

export default function PoolList() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
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
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'flex-end' }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsModalOpen(true)}>
          新建池
        </Button>
      </div>

      <GlassCard>
        <Table
          dataSource={pools || []}
          columns={columns}
          rowKey="id"
          onRow={(record) => ({
            onClick: () => navigate(`/pools/${record.id}`),
            style: { cursor: 'pointer' },
          })}
          pagination={false}
        />
      </GlassCard>

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
    </div>
  );
}
