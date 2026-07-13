import { useState } from 'react';
import {
  Table,
  Button,
  Modal,
  Form,
  Input,
  Select,
  Switch,
  Space,
  Tooltip,
  message,
  Popconfirm,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  KeyOutlined,
} from '@ant-design/icons';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import SectionHeading from '@/components/SectionHeading';
import ThemeTag from '@/components/ThemeTag';
import { useAdminUsers } from '@/hooks/useAdminUsers';
import { useAuthStore } from '@/stores/auth';
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion';
import type { UserAdminItem } from '@/types/user';

const ROLE_OPTIONS = [
  { label: '管理员', value: 'admin' },
  { label: '普通用户', value: 'user' },
];

export default function AdminUsers() {
  const { user: currentUser } = useAuthStore();
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [isResetOpen, setIsResetOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<UserAdminItem | null>(null);
  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();
  const [resetForm] = Form.useForm();
  const reducedMotion = usePrefersReducedMotion();
  const modalMotionProps = reducedMotion
    ? { transitionName: '', maskTransitionName: '' }
    : {};

  const {
    users,
    isLoading,
    create,
    update,
    delete: deleteUser,
    resetPassword,
  } = useAdminUsers();

  const isSelf = (record: UserAdminItem) => record.username === currentUser?.username;

  const handleCreate = async (values: any) => {
    try {
      await create({
        username: values.username,
        password: values.password,
        role: values.role,
        is_active: values.is_active,
      });
      message.success('用户创建成功');
      setIsCreateOpen(false);
      createForm.resetFields();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '创建失败');
    }
  };

  const handleEdit = async (values: any) => {
    if (!editingUser) return;
    try {
      await update({
        id: editingUser.id,
        data: {
          role: values.role,
          is_active: values.is_active,
        },
      });
      message.success('更新成功');
      setIsEditOpen(false);
      setEditingUser(null);
      editForm.resetFields();
    } catch {
      message.error('更新失败');
    }
  };

  const handleDelete = async (record: UserAdminItem) => {
    try {
      await deleteUser(record.id);
      message.success('删除成功');
    } catch {
      message.error('删除失败');
    }
  };

  const handleResetPassword = async (values: any) => {
    if (!editingUser) return;
    try {
      await resetPassword({
        id: editingUser.id,
        data: { new_password: values.new_password },
      });
      message.success('密码重置成功');
      setIsResetOpen(false);
      setEditingUser(null);
      resetForm.resetFields();
    } catch {
      message.error('密码重置失败');
    }
  };

  const openEdit = (record: UserAdminItem) => {
    setEditingUser(record);
    editForm.setFieldsValue({
      role: record.role,
      is_active: record.is_active,
    });
    setIsEditOpen(true);
  };

  const openReset = (record: UserAdminItem) => {
    setEditingUser(record);
    resetForm.resetFields();
    setIsResetOpen(true);
  };

  const columns: ColumnsType<UserAdminItem> = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '用户名', dataIndex: 'username' },
    {
      title: '角色',
      dataIndex: 'role',
      width: 100,
      render: (v: string) =>
        v === 'admin' ? (
          <ThemeTag variant="accent">管理员</ThemeTag>
        ) : (
          <ThemeTag variant="default">普通用户</ThemeTag>
        ),
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      width: 90,
      render: (v: boolean) =>
        v ? <ThemeTag variant="success">启用</ThemeTag> : <ThemeTag variant="default">禁用</ThemeTag>,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      render: (v: string) => (v ? new Date(v).toLocaleString('zh-CN') : '-'),
    },
    {
      title: '操作',
      key: 'action',
      width: 180,
      fixed: 'right',
      render: (_: any, record: UserAdminItem) => {
        const self = isSelf(record);
        const tooltipTitle = self ? '不能修改自己的账号' : '';
        return (
          <Space>
            <Tooltip title={self ? tooltipTitle : ''}>
              <Button
                size="small"
                icon={<EditOutlined />}
                onClick={() => openEdit(record)}
                disabled={self}
              >
                编辑
              </Button>
            </Tooltip>
            <Tooltip title={self ? tooltipTitle : '重置该用户密码'}>
              <Button
                size="small"
                type="text"
                icon={<KeyOutlined />}
                onClick={() => openReset(record)}
                disabled={self}
                aria-label="重置密码"
              />
            </Tooltip>
            <Popconfirm
              title="确认删除"
              description={`确定要删除用户 ${record.username} 吗？`}
              onConfirm={() => handleDelete(record)}
              okText="删除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
              disabled={self}
            >
              <Tooltip title={self ? tooltipTitle : ''}>
                <Button
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  disabled={self}
                >
                  删除
                </Button>
              </Tooltip>
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  return (
    <PageShell maxWidth="wide">
      <PageHeader
        title="用户管理"
        description="管理平台用户账号，配置角色权限与启用状态"
        extra={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setIsCreateOpen(true)}
          >
            新增用户
          </Button>
        }
      />

      <SectionHeading title="用户列表" />
      <Panel variant="default" padding="md">
        <Table
          dataSource={users}
          columns={columns}
          rowKey="id"
          size="small"
          loading={isLoading}
          scroll={{ x: 'max-content' }}
          pagination={false}
        />
      </Panel>

      {/* Create Modal */}
      <Modal
        title="新增用户"
        open={isCreateOpen}
        onCancel={() => {
          setIsCreateOpen(false);
          createForm.resetFields();
        }}
        onOk={() => createForm.submit()}
        width={480}
        destroyOnClose
        {...modalMotionProps}
      >
        <Form
          form={createForm}
          layout="vertical"
          onFinish={handleCreate}
          initialValues={{ role: 'user', is_active: true }}
        >
          <Form.Item
            name="username"
            label="用户名"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input placeholder="用户名" />
          </Form.Item>
          <Form.Item
            name="password"
            label="密码"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password placeholder="初始密码" />
          </Form.Item>
          <Form.Item
            name="role"
            label="角色"
            rules={[{ required: true, message: '请选择角色' }]}
          >
            <Select options={ROLE_OPTIONS} />
          </Form.Item>
          <Form.Item
            name="is_active"
            label="启用状态"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      {/* Edit Modal */}
      <Modal
        title="编辑用户"
        open={isEditOpen}
        onCancel={() => {
          setIsEditOpen(false);
          setEditingUser(null);
          editForm.resetFields();
        }}
        onOk={() => editForm.submit()}
        width={400}
        destroyOnClose
        {...modalMotionProps}
      >
        <Form form={editForm} layout="vertical" onFinish={handleEdit}>
          <Form.Item
            name="role"
            label="角色"
            rules={[{ required: true, message: '请选择角色' }]}
          >
            <Select options={ROLE_OPTIONS} />
          </Form.Item>
          <Form.Item
            name="is_active"
            label="启用状态"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      {/* Reset Password Modal */}
      <Modal
        title={`重置密码 - ${editingUser?.username || ''}`}
        open={isResetOpen}
        onCancel={() => {
          setIsResetOpen(false);
          setEditingUser(null);
          resetForm.resetFields();
        }}
        onOk={() => resetForm.submit()}
        width={400}
        destroyOnClose
        {...modalMotionProps}
      >
        <Form form={resetForm} layout="vertical" onFinish={handleResetPassword}>
          <Form.Item
            name="new_password"
            label="新密码"
            rules={[{ required: true, message: '请输入新密码' }]}
          >
            <Input.Password placeholder="新密码" />
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}
