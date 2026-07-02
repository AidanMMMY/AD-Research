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
        className="ai-setup-banner ai-setup-banner__warning"
        message={
          <div className="ai-setup-banner__message">
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
              className="ai-setup-banner__button"
            >
              获取 API Key
            </Button>
          </div>
        }
        description={
          <span className="ai-setup-banner__description">
            在 <code>.env</code> 中设置 <code>DEEPSEEK_API_KEY=sk-...</code> 后重启服务即可激活。
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
      className="ai-setup-banner ai-setup-banner__info"
      message={
        <span>
          AI 已就绪 — 使用 <ThemeTag variant="neutral" style={{ margin: '0 4px' }}>{status.provider} {status.model}</ThemeTag>
        </span>
      }
    />
  );
}
