import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export function AnswerMarkdown({ children }: { children: string }) {
  return (
    <div className="answer markdown-answer">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ children: label, ...props }) => (
            <a {...props} target="_blank" rel="noreferrer">{label}</a>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  )
}
