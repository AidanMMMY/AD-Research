import { useMemo, useState } from 'react';
import {
  Button,
  Drawer,
  Form,
  Input,
  InputNumber,
  Popconfirm,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import { EditOutlined, DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import Panel from '@/components/Panel';
import { useCreateTemplate, useDeleteTemplate, useScoreTemplates, useUpdateTemplate } from '@/hooks/useScores';
import type { ScoreTemplate } from '@/types/score';

const { Text } = Typography;

/** Fixed dimension set the backend calculator understands. */
const DIMENSION_KEYS = ['return', 'risk', 'sharpe', 'liquidity', 'trend'] as const;
type DimensionKey = (typeof DIMENSION_KEYS)[number];

const DIMENSION_LABEL: Record<DimensionKey, string> = {
  return: '收益',
  risk: '风险',
  sharpe: '夏普',
  liquidity: '流动性',
  trend: '趋势',
};

const DEFAULT_WEIGHTS: Record<DimensionKey, number> = {
  return: 0.3,
  risk: 0.25,
  sharpe: 0.25,
  liquidity: 0.1,
  trend: 0.1,
};

interface FormState {
  name: string;
  description?: string;
  is_default: boolean;
  /** Only the dimensions the user actively set will be sent. */
  weights: Record<string, number>;
}

/** Build initial form state for either a new template or an existing one. */
function buildInitial(record?: ScoreTemplate | null): FormState {
  if (record) {
    return {
      name: record.name,
      description: record.description ?? '',
      is_default: !!record.is_default,
      // Only keep known dimension keys; ignore legacy/unknown ones.
      weights: Object.fromEntries(
        DIMENSION_KEYS.filter((k) => record.weights[k] != null).map((k) => [k, record.weights[k]]),
      ) as Record<string, number>,
    };
  }
  return {
    name: '',
    description: '',
    is_default: false,
    weights: { ...DEFAULT_WEIGHTS },
  };
}

export default function TemplateManagement() {
  const { data: templates, isLoading } = useScoreTemplates();
  const createMut = useCreateTemplate();
  const updateMut = useUpdateTemplate();
  const deleteMut = useDeleteTemplate();

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<ScoreTemplate | null>(null);
  const [form] = Form.useForm<FormState>();
  // Watch the is_default field so the switch is disabled when editing a default.
  const isDefaultValue = Form.useWatch('is_default', form);

  const openCreate = () => {
    setEditing(null);
    form.setFieldsValue(buildInitial(null));
    setDrawerOpen(true);
  };

  const openEdit = (t: ScoreTemplate) => {
    setEditing(t);
    form.setFieldsValue(buildInitial(t));
    setDrawerOpen(true);
  };

  const closeDrawer = () => {
    setDrawerOpen(false);
    setEditing(null);
    form.resetFields();
  };

  const onSubmit = async () => {
    let values: FormState;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    // Strip zero / negative weights so the backend only receives active dimensions.
    const cleanWeights: Record<string, number> = {};
    for (const k of DIMENSION_KEYS) {
      const w = Number(values.weights?.[k] ?? 0);
      if (Number.isFinite(w) && w > 0) cleanWeights[k] = w;
    }
    if (Object.keys(cleanWeights).length === 0) {
      message.warning('请至少设置一个维度的权重');
      return;
    }
    const payload = {
      name: values.name.trim(),
      description: values.description?.trim() || undefined,
      is_default: values.is_default,
      weights: cleanWeights,
    };
    try {
      if (editing) {
        await updateMut.mutateAsync({ id: editing.id, data: payload });
      } else {
        await createMut.mutateAsync(payload);
      }
      closeDrawer();
    } catch {
      // Toast already shown in hook onError.
    }
  };

  const onDelete = async (t: ScoreTemplate) => {
    try {
      await deleteMut.mutateAsync(t.id);
    } catch {
      // Toast already shown.
    }
  };

  const weightSummary = useMemo(
    () => (w: Record<string, number>) => {
      const parts = DIMENSION_KEYS.filter((k) => w[k] != null && w[k] > 0).map(
        (k) => `${DIMENSION_LABEL[k]}=${(w[k] * 100).toFixed(0)}%`,
      );
      return parts.length > 0 ? parts.join(' / ') : '—';
    },
    [],
  );

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      width: 180,
      render: (v: string, record: ScoreTemplate) => (
        <Space size={6}>
          <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{v}</span>
          {record.is_default && <Tag color="accent">默认</Tag>}
        </Space>
      ),
    },
    {
      title: '维度',
      key: 'dimensions',
      render: (_: unknown, record: ScoreTemplate) => (
        <span style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
          {DIMENSION_KEYS.filter((k) => record.weights[k] != null && record.weights[k] > 0).join(' / ') || '—'}
        </span>
      ),
    },
    {
      title: '权重',
      key: 'weights',
      render: (_: unknown, record: ScoreTemplate) => (
        <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{weightSummary(record.weights)}</span>
      ),
    },
    {
      title: '默认',
      dataIndex: 'is_default',
      width: 80,
      render: (v: boolean) => (v ? <Tag color="accent">是</Tag> : <Text type="secondary">否</Text>),
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      render: (_: unknown, record: ScoreTemplate) => (
        <Space size={4}>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>
            编辑
          </Button>
          {record.is_default ? (
            <Tooltip title="默认模板不可删除">
              <Button type="link" size="small" danger icon={<DeleteOutlined />} disabled>
                删除
              </Button>
            </Tooltip>
          ) : (
            <Popconfirm
              title="确认删除该模板？"
              description="删除后基于该模板的历史评分仍会保留，但无法再生成新评分。"
              okText="删除"
              okType="danger"
              cancelText="取消"
              onConfirm={() => onDelete(record)}
            >
              <Button type="link" size="small" danger icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  // Disabled flag: default templates cannot be untoggled (per task spec).
  const isDefaultLocked = !!editing?.is_default;

  return (
    <div>
      <Panel
        variant="minimal"
        title="模板管理"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新建模板
          </Button>
        }
      >
        <Table
          dataSource={templates ?? []}
          columns={columns}
          rowKey="id"
          size="small"
          loading={isLoading}
          pagination={false}
          scroll={{ x: 'max-content' }}
          expandable={{
            expandedRowRender: (record: ScoreTemplate) => (
              <pre
                style={{
                  margin: 0,
                  padding: 12,
                  background: 'var(--bg-elevated)',
                  border: '1px solid var(--border-default)',
                  borderRadius: 4,
                  fontSize: 12,
                  color: 'var(--text-secondary)',
                  overflow: 'auto',
                }}
              >
                {JSON.stringify(record, null, 2)}
              </pre>
            ),
            rowExpandable: () => true,
          }}
        />
      </Panel>

      <Drawer
        title={editing ? `编辑模板 — ${editing.name}` : '新建评分模板'}
        open={drawerOpen}
        onClose={closeDrawer}
        width={480}
        destroyOnClose
        extra={
          <Space>
            <Button onClick={closeDrawer}>取消</Button>
            <Button
              type="primary"
              loading={createMut.isPending || updateMut.isPending}
              onClick={onSubmit}
            >
              保存
            </Button>
          </Space>
        }
      >
        <Form<FormState> form={form} layout="vertical" requiredMark="optional">
          <Form.Item
            name="name"
            label="模板名称"
            rules={[
              { required: true, message: '请输入模板名称' },
              { max: 50, message: '名称不能超过 50 字符' },
            ]}
          >
            <Input placeholder="如：稳健型、激进型" maxLength={50} showCount />
          </Form.Item>

          <Form.Item name="description" label="说明">
            <Input.TextArea
              placeholder="可选：描述该模板的适用场景"
              autoSize={{ minRows: 2, maxRows: 4 }}
              maxLength={200}
              showCount
            />
          </Form.Item>

          <Form.Item
            name="is_default"
            label="设为默认模板"
            valuePropName="checked"
            tooltip={isDefaultLocked ? '默认模板不可取消默认状态' : undefined}
          >
            <Switch disabled={isDefaultLocked} />
          </Form.Item>

          <div style={{ marginTop: 8, marginBottom: 12, color: 'var(--text-tertiary)', fontSize: 12 }}>
            维度权重（0 表示不参与评分；同模板内权重不要求和为 1，服务端会按各维度的权重计算综合分）
          </div>

          {DIMENSION_KEYS.map((k) => (
            <Form.Item
              key={k}
              name={['weights', k]}
              label={DIMENSION_LABEL[k]}
              initialValue={DEFAULT_WEIGHTS[k]}
              rules={[{ type: 'number', min: 0, max: 1, message: '范围 0–1' }]}
            >
              <InputNumber<number>
                min={0}
                max={1}
                step={0.05}
                style={{ width: 160 }}
                formatter={(v) => (v != null ? `${(Number(v) * 100).toFixed(0)}%` : '')}
                parser={(v) => {
                  const s = (v ?? '').replace(/[^\d.]/g, '');
                  const n = Number(s);
                  return (Number.isFinite(n) ? n : 0) / 100;
                }}
              />
            </Form.Item>
          ))}

          {isDefaultValue && !isDefaultLocked && (
            <Text type="warning" style={{ fontSize: 12 }}>
              将此模板设为默认后，评分排名页将默认使用此模板进行排序。
            </Text>
          )}
        </Form>
      </Drawer>
    </div>
  );
}
