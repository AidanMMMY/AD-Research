import { useQuery } from '@tanstack/react-query';
import { Alert, Button } from 'antd';
import { ApiOutlined, KeyOutlined } from '@ant-design/icons';
import { researchApi } from '@/api/research';
import ThemeTag from '@/components/ThemeTag';

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
        style={{
          marginBottom: 16,
          borderRadius: 12,
          background: 'var(--color-warning-dim)',
          border: '1px solid var(--color-warning-border)',
        }}
        message={
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
            <span>
              <strong>AI 功能未配置</strong>
              <span style={{ color: 'var(--text-secondary)', marginLeft: 8 }}>
                当前模型 <ThemeTag variant="neutral" style={{ margin: '0 4px' }}>{status.provider} / {status.model}</ThemeTag>
                预估成本 <ThemeTag variant="success" style={{ margin: '0 4px' }}>{status.monthly_cost_estimate}</ThemeTag>
              </span>
            </span>
            <Button
              type="primary"
              size="small"
              icon={<ApiOutlined />}
              href={status.setup_url}
              target="_blank"
              style={{ background: 'var(--accent)', border: 'none' }}
            >
              获取 API Key
            </Button>
          </div>
        }
        description={
          <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
            在 <code style={{ background: 'var(--bg-input)', padding: '1px 6px', borderRadius: 4 }}>.env</code> 中设置 <code style={{ background: 'var(--bg-input)', padding: '1px 6px', borderRadius: 4 }}>DEEPSEEK_API_KEY=sk-REMOVED-...</code> 后重启服务即可激活。
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
      style={{
        marginBottom: 16,
        borderRadius: 12,
        background: 'var(--accent-dim)',
        border: '1px solid var(--accent-border)',
      }}
      message={
        <span>
          AI 已就绪 — 使用 <ThemeTag variant="neutral" style={{ margin: '0 4px' }}>{status.provider} {status.model}</ThemeTag>
        </span>
      }
    />
  );
}
