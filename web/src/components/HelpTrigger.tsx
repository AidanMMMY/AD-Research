import { Button, Tooltip } from 'antd';
import { QuestionCircleOutlined, RobotOutlined } from '@ant-design/icons';
import type { HelpTriggerProps } from '@/types/help';

export default function HelpTrigger({
  onClick,
  tooltip = 'AI 解释',
  size = 'small',
  style,
  className,
}: HelpTriggerProps) {
  const iconSize = size === 'small' ? 14 : 16;
  const buttonSize: 'small' | 'middle' = size === 'small' ? 'small' : 'middle';

  return (
    <Tooltip title={tooltip} placement="top">
      <Button
        type="text"
        size={buttonSize}
        className={className}
        onClick={onClick}
        icon={
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <RobotOutlined style={{ fontSize: iconSize, color: '#818cf8' }} />
            <QuestionCircleOutlined style={{ fontSize: iconSize - 2, color: '#94a3b8' }} />
          </span>
        }
        style={{
          color: '#94a3b8',
          padding: size === 'small' ? '0 6px' : '0 8px',
          height: size === 'small' ? 28 : 32,
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          borderRadius: 8,
          ...style,
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.color = '#e2e8f0';
          e.currentTarget.style.background = 'rgba(99,102,241,0.1)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.color = '#94a3b8';
          e.currentTarget.style.background = 'transparent';
        }}
      />
    </Tooltip>
  );
}
