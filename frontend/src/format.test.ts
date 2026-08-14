import { describe, expect, it } from 'vitest'
import { formatDateTime, uzbekDeadline } from './format'

describe('O‘zbekiston sana va vaqt yordamchilari', () => {
  it('Toshkent vaqtini aniq ISO vaqtiga aylantiradi', () => {
    expect(uzbekDeadline('13.08.2026', '17:45')).toBe('2026-08-13T12:45:00.000Z')
  })

  it('mavjud bo‘lmagan sanani rad etadi', () => {
    expect(() => uzbekDeadline('31.02.2026', '10:00')).toThrow('Muddat sanasi yoki vaqti noto‘g‘ri')
  })

  it('server vaqtini 24-soatli Toshkent vaqtida ko‘rsatadi', () => {
    expect(formatDateTime('2026-08-13T12:45:00.000Z')).toMatch(/13.*08.*2026.*17:45/)
  })
})
