import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { AnswerMarkdown } from './AnswerMarkdown'

describe('AI javobining xavfsiz Markdown ko‘rinishi', () => {
  it('qalin matn, ro‘yxat va GFM jadvalini HTMLga aylantiradi', () => {
    const html = renderToStaticMarkup(
      <AnswerMarkdown>{'**19-modda**\n\n- Birinchi band\n\n| Ustun | Qiymat |\n|---|---|\n| A | B |'}</AnswerMarkdown>,
    )
    expect(html).toContain('<strong>19-modda</strong>')
    expect(html).toContain('<li>Birinchi band</li>')
    expect(html).toContain('<table>')
  })

  it('model qaytargan xom HTMLni bajariladigan elementga aylantirmaydi', () => {
    const html = renderToStaticMarkup(<AnswerMarkdown>{'<script>alert(1)</script>'}</AnswerMarkdown>)
    expect(html).not.toContain('<script>')
  })
})
