import { Card } from 'antd';
import type { CardProps } from 'antd/es/card';

export interface ContentCardProps extends CardProps {}

/**
 * @deprecated Use `@/components/Panel` instead. Scheduled for removal once
 * the remaining consumer (pages/NewsHealth) is migrated off it.
 */
export default function ContentCard({ className, ...props }: ContentCardProps) {
  return <Card className={`content-card ${className || ''}`.trim()} {...props} />;
}
