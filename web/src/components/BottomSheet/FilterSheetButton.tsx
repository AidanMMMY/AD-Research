import { useState } from 'react';
import type { ReactNode } from 'react';
import { Badge, Button } from 'antd';
import { FilterOutlined } from '@ant-design/icons';
import BottomSheet from './BottomSheet';

export interface FilterSheetButtonProps {
  /** Number of active filters — shown as a badge on the trigger. */
  activeCount?: number;
  /** Sheet title. Default 「筛选」. */
  title?: ReactNode;
  /** Optional meta shown in the sheet header (e.g. 共 N 只). */
  meta?: ReactNode;
  /** Reset handler — renders a 「重置」 text button in the sheet header. */
  onReset?: () => void;
  /** Trigger button label. Default 「筛选」. */
  buttonText?: ReactNode;
  /** Sheet detents — default ['half', 'full'] (see BottomSheet). */
  snaps?: ('peek' | 'half' | 'full')[];
  /** The full filter form, rendered inside the sheet body. */
  children: ReactNode;
}

/**
 * 「筛选」trigger button + half-sheet hosting the complete filter form
 * (P3 / 方向 C: the inline FilterToolbar is desktop-only; on mobile the
 * first screen belongs to the list, filters live one tap away).
 *
 * Filters apply live — the list under the scrim refreshes as controls
 * change — so the footer is a plain 「完成」close affordance rather than
 * an apply/cancel pair (no staged state to commit).
 */
export default function FilterSheetButton({
  activeCount = 0,
  title = '筛选',
  meta,
  onReset,
  buttonText = '筛选',
  snaps,
  children,
}: FilterSheetButtonProps) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Badge
        count={activeCount}
        size="small"
        offset={[-4, 4]}
        aria-label={activeCount > 0 ? `${activeCount} 个活跃筛选条件` : undefined}
      >
        <Button
          icon={<FilterOutlined />}
          onClick={() => setOpen(true)}
          aria-haspopup="dialog"
          aria-expanded={open}
        >
          {buttonText}
        </Button>
      </Badge>
      <BottomSheet
        open={open}
        onClose={() => setOpen(false)}
        title={title}
        snaps={snaps}
        footer={
          <Button type="primary" block onClick={() => setOpen(false)}>
            完成
          </Button>
        }
      >
        {(meta || onReset) && (
          <div className="ad-flex ad-items-center ad-gap-2 ad-mb-3">
            {meta ? (
              <span className="ad-text-small ad-text-tertiary">{meta}</span>
            ) : null}
            <span className="ad-flex-1" />
            {onReset ? (
              <Button type="link" size="small" onClick={onReset}>
                重置
              </Button>
            ) : null}
          </div>
        )}
        <div className="filter-sheet-body">{children}</div>
      </BottomSheet>
    </>
  );
}
