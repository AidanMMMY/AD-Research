import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Tag } from 'antd';
import { ApiOutlined, KeyOutlined } from '@ant-design/icons';
import { researchApi } from '@/api/research';

interface AISetupBannerProps {
  /** If true, only check and show banner when unavailable. If false, always show info. */
  onlyWhenUnavailable?: boolean;
}

export function useAIStatus() {
  return useQuery({
    queryKey: ['ai-status'],
    queryFn: () => researchApi.getAIStatus().then((r) => r.data),
    staleTime: 300_000, // 5 minutes
  });
}

export default function AISetupBanner({ onlyWhenUnavailable = true }: AISetupBannerProps) {
  const { data: status, isLoading } = useAIStatus();

  if (isLoading) return null;
  if (!status) return null;
  if (onlyWhenUnavailable && status.available) return null;

  if (!status.available) {
    return (
      <Alert
        type="warning"
        showIcon
        icon={<KeyOutlined />}
        style={{ marginBottom: 16, borderRadius: 12, background: 'rgba(234,179,8,0.08)', border: '1px solid rgba(234,179,8,0.2)' }}
        message={
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
            <span>
              <strong>AI 功能未配置</strong>
              <span style={{ color: '#94a3b8', marginLeft: 8 }}>
                当前模型 <Tag style={{ margin: '0 4px' }}>{status.provider} / {status.model}</Tag>
                预估成本 <Tag color="green" style={{ margin: '0 4px' }}>{status.monthly_cost_estimate}</Tag>
              </span>
            </span>
            <Button
              type="primary"
              size="small"
              icon={<ApiOutlined />}
              href={status.setup_url}
              target="_blank"
              style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)', border: 'none' }}
            >
              获取 API Key
            </Button>
          </div>
        }
        description={
          <span style={{ fontSize: 12, color: '#64748b' }}>
            在 <code style={{ background: 'rgba(255,255,255,0.06)', padding: '1px 6px', borderRadius: 4 }}>.env</code> 中设置 <code style={{ background: 'rgba(255,255,255,0.06)', padding: '1px 6px', borderRadius: 4 }}>DEEPSEEK_API_KEY=sk-...</code> 后重启服务即可激活。
          </span>
        }
      />
    );
  }

  return (
    <Alert
      type="info"
      showIcon
      icon={<ApiOutlined />}
      style={{ marginBottom: 16, borderRadius: 12, background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.15)' }}
      message={
        <span>
          AI 已就绪 — 使用 <Tag style={{ margin: '0 4px' }}>{status.provider} {status.model}</Tag>
        </span>
      }
    />
  );
}
