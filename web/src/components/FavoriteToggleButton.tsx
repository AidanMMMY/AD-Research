import { StarOutlined, StarFilled } from '@ant-design/icons';
import { Tooltip } from 'antd';
import { useFavoriteStatus } from '@/hooks/useFavorites';

interface Props {
  code: string;
  name?: string;
}

/**
 * Compact "★" toggle used in tables / cards where the full-width
 * InstrumentDetail "已收藏/收藏" button would dominate. Shares the same
 * `useFavoriteStatus` hook and favorite API as the detail page, so the
 * star state stays in sync across the app.
 */
export default function FavoriteToggleButton({ code, name }: Props) {
  const { isFavorite, toggle, isToggling } = useFavoriteStatus(code || '');

  const handleClick = async (e: React.MouseEvent) => {
    // Stop the parent <Table onRow.onClick> from also firing and
    // navigating away when the user clicks the star.
    e.stopPropagation();
    try {
      await toggle();
    } catch {
      /* the hook surfaces isToggling; we swallow the error silently here
         to keep the click handler responsive in dense table rows */
    }
  };

  return (
    <Tooltip title={isFavorite ? '取消自选' : '加入自选'}>
      <button
        type="button"
        onClick={handleClick}
        disabled={isToggling}
        aria-label={isFavorite ? `取消自选 ${name || code}` : `加入自选 ${name || code}`}
        style={{
          background: 'transparent',
          border: 0,
          cursor: isToggling ? 'wait' : 'pointer',
          color: isFavorite ? 'var(--color-warning)' : 'var(--text-tertiary)',
          fontSize: 16,
          padding: 4,
          lineHeight: 1,
        }}
      >
        {isFavorite ? <StarFilled /> : <StarOutlined />}
      </button>
    </Tooltip>
  );
}