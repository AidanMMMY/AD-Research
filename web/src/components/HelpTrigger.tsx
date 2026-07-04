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
  const buttonSize: 'small' | 'middle' = size === 'small' ? 'small' : 'middle';

  return (
    <Tooltip title={tooltip} placement="top">
      <Button
        type="text"
        size={buttonSize}
        className={`help-trigger help-trigger--${buttonSize} ${className || ''}`}
        onClick={onClick}
        style={style}
        icon={
          <span className="help-trigger__icons">
            <RobotOutlined className="help-trigger__icon-ai" />
            <QuestionCircleOutlined className="help-trigger__icon-help" />
          </span>
        }
      />
    </Tooltip>
  );
}
