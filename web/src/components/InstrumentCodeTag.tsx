import { Tooltip } from 'antd';

interface InstrumentCodeTagProps {
  code: string;
  name?: string;
  /** Optional Chinese display name (shown as a smaller grey line under the English name). */
  name_zh?: string | null;
}

export default function InstrumentCodeTag({ code, name, name_zh }: InstrumentCodeTagProps) {
  const tooltipBody = name_zh
    ? `${name || code} (${name_zh})`
    : (name || code);

  return (
    <Tooltip title={tooltipBody}>
      <div className="instrument-code-tag">
        <span className="instrument-code-tag__code">
          {code}
        </span>
        {name && (
          <span className="instrument-code-tag__name">
            {name}
          </span>
        )}
        {name_zh && (
          <span className="instrument-code-tag__name-zh">
            {name_zh}
          </span>
        )}
      </div>
    </Tooltip>
  );
}
