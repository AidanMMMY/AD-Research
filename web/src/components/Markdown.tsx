import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/**
 * Lightweight Markdown renderer used wherever we render text returned
 * by AI / Jina Reader / news captions. Keeps a consistent look across
 * pages and gives us one place to tweak typography later.
 */
export default function Markdown({ source }: { source: string }) {
  return (
    <div
      style={{
        fontSize: 15,
        lineHeight: 1.7,
        color: 'var(--text-primary)',
        wordBreak: 'break-word',
      }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {source}
      </ReactMarkdown>
    </div>
  );
}
