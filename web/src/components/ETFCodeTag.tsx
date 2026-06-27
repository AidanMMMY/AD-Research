import { Tooltip } from 'antd';

interface ETFCodeTagProps {
  code: string;
  name?: string;
}

export default function ETFCodeTag({ code, name }: ETFCodeTagProps) {
  return (
    <Tooltip title={name || code}>
      <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
        <span
          style={{
            display: 'inline-block',
            padding: '2px 8px',
            borderRadius: 'var(--radius-sm)',
            fontSize: 'var(--text-code-size)',
            fontWeight: 500,
            fontFamily: 'var(--font-mono)',
            color: 'var(--accent)',
            background: 'var(--accent-dim)',
            border: '1px solid var(--accent-border)',
            letterSpacing: '0.02em',
          }}
        >
          {code}
        </span>
        {name && (
          <span
            style={{
              fontSize: 'var(--text-body-size)',
              color: 'var(--text-secondary)',
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
