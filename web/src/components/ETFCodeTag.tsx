import { Tooltip } from 'antd';

interface ETFCodeTagProps {
  code: string;
  name?: string;
}

export default function ETFCodeTag({ code, name }: ETFCodeTagProps) {
  return (
    <Tooltip title={name || code}>
      <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
        <span
          style={{
            display: 'inline-block',
            padding: '3px 10px',
            borderRadius: 6,
            fontSize: 12,
            fontWeight: 700,
            fontFamily: "'SF Mono', 'Fira Code', monospace",
            color: '#818cf8',
            background: 'rgba(99, 102, 241, 0.12)',
            border: '1px solid rgba(99, 102, 241, 0.2)',
            letterSpacing: '0.3px',
          }}
        >
          {code}
        </span>
        {name && (
          <span
            style={{
              fontSize: 13,
              color: '#94a3b8',
              fontWeight: 400,
              maxWidth: 160,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {name}
          </span>
        )}
      </div>
    </Tooltip>
  );
}
