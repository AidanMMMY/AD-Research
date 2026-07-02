import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/**
 * Lightweight Markdown renderer used wherever we render text returned
 * by AI / Jina Reader / news captions. Keeps a consistent look across
 * pages and gives us one place to tweak typography later.
 */
export default function Markdown({ source }: { source: string }) {
  return (
    <div className="ad-markdown">
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
