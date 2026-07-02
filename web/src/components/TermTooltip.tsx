import { Tooltip } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';
import { getTerm } from '@/utils/termDictionary';

interface TermTooltipProps {
  /** 术语 key，对应 termDictionary 中的 key */
  termKey: string;
  /** 自定义显示文本，默认使用词典中的 title */
  children?: React.ReactNode;
  /** 是否显示右侧小 info 图标 */
  showIcon?: boolean;
  /** Tooltip 位置 */
  placement?: 'top' | 'bottom' | 'left' | 'right';
  /** 自定义样式 */
  style?: React.CSSProperties;
  /** 是否启用，默认 true */
  enabled?: boolean;
}

export default function TermTooltip({
  termKey,
  children,
  showIcon = false,
  placement = 'top',
  style,
  enabled = true,
}: TermTooltipProps) {
  const term = getTerm(termKey);

  if (!enabled || !term) {
    return <span style={style}>{children}</span>;
  }

  return (
    <Tooltip
      title={term.shortDesc}
      placement={placement}
      overlayStyle={{ maxWidth: 320 }}
    >
      <span
        className="term-tooltip"
        style={style}
      >
        {children || term.title}
        {showIcon && (
          <InfoCircleOutlined
            className="term-tooltip__icon"
          />
        )}
      </span>
    </Tooltip>
  );
}
