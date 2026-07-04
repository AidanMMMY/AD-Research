import { Tooltip } from 'antd';

interface InstrumentCodeTagProps {
  code: string;
  name?: string | null;
  /** Optional Chinese display name (shown as a smaller grey line under the English name). */
  name_zh?: string | null;
}

/**
 * 标的代码 + 名称 + 中文名 三段式标签。
 *
 * - 颜色 / 间距 / 圆角 / 字号 全部走 token (`--accent` / `--space-2` /
 *   `--text-code-size` / `--text-body-size` / `--text-small-size`)。
 * - light/dark + China/US 颜色约定自动跟随。
 * - 移动端通过 CSS media query 自动收紧 name 列宽。
 */
export default function InstrumentCodeTag({ code, name, name_zh }: InstrumentCodeTagProps) {
  const tooltipBody = name_zh
    ? `${name || code} (${name_zh})`
    : (name || code);

  return (
    <Tooltip title={tooltipBody}>
      <span className="instrument-code-tag">
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