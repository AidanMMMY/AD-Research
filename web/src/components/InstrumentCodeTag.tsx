import { Tooltip } from 'antd';

interface InstrumentCodeTagProps {
  code: string;
  name?: string;
}

export default function InstrumentCodeTag({ code, name }: InstrumentCodeTagProps) {
  return (
    <Tooltip title={name || code}>
      <div className="instrument-code-tag">
        <span className="instrument-code-tag__code">
          {code}
        </span>
        {name && (
          <span className="instrument-code-tag__name">
            {name}
          </span>
        )}
      </div>
    </Tooltip>
  );
}
