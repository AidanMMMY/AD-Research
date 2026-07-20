import { useNavigate } from 'react-router-dom';
import { Button } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import EmptyState from '@/components/EmptyState';

/**
 * Catch-all 404 page for unknown URLs (renders inside AppLayout).
 */
export default function NotFound() {
  const navigate = useNavigate();
  return (
    <EmptyState
      icon={<QuestionCircleOutlined />}
      title="页面不存在"
      description="你访问的地址不存在或已被移除，请检查链接是否正确。"
      action={
        <Button type="primary" onClick={() => navigate('/dashboard')}>
          返回首页
        </Button>
      }
    />
  );
}
