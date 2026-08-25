import { Tooltip } from 'antd';
import './InstrumentCodeTag.css';

interface InstrumentCodeTagProps {
  code: string;
  name?: string | null;
  /** Optional Chinese display name (shown as a smaller grey line under the English name). */
  name_zh?: string | null;
  /**
   * 视觉变体：
   * - accent（默认）：accent 底色代码块，用于列表中可跳转/强调的标的 chip；
   * - static：中性变体（无 accent 底色/边框、默认光标），用于纯展示场景
   *   （如标的详情页 hero 区、无对应详情页的期货合约），避免假可点外观。
   */
  variant?: 'accent' | 'static';
}

/**
 * 标的代码 + 名称 + 中文名 三段式标签。
 *
 * - 颜色 / 间距 / 圆角 / 字号 全部走 token (`--accent` / `--space-2` /
 *   `--text-code-size` / `--text-body-size` / `--text-small-size`)。
 * - light/dark + China/US 颜色约定自动跟随。
 * - 移动端通过 CSS media query 自动收紧 name 列宽。
 */
export default function InstrumentCodeTag({ code, name, name_zh, variant = 'accent' }: InstrumentCodeTagProps) {
  const tooltipBody = name_zh
    ? `${name || code} (${name_zh})`
    : (name || code);

  return (
    <Tooltip title={tooltipBody}>
      <span className={`instrument-code-tag${variant === 'static' ? ' instrument-code-tag--static' : ''}`}>
        <span className="instrument-code-tag__code">
          {code}
        </span>
        {name ? (
          <span className="instrument-code-tag__name">
            {name}
          </span>
        ) : null}
        {name_zh ? (
          <span className="instrument-code-tag__name-zh">
            {name_zh}
          </span>
        ) : null}
      </span>
    </Tooltip>
  );
}
