import { Card } from 'antd';
import type { CardProps } from 'antd/es/card';

export interface ContentCardProps extends CardProps {}

export default function ContentCard({ className, ...props }: ContentCardProps) {
  return <Card className={`content-card ${className || ''}`.trim()} {...props} />;
}
