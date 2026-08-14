const months = ['yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun', 'iyul', 'avgust', 'sentabr', 'oktabr', 'noyabr', 'dekabr']

export function shortDate(value: string): string {
  const date = new Date(value)
  return `${date.getDate()}-${months[date.getMonth()]}`
}

export function formatDateTime(value: string): string {
  const parts = new Intl.DateTimeFormat('en-GB', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
    hour12: false, hourCycle: 'h23', timeZone: 'Asia/Tashkent',
  }).formatToParts(new Date(value))
  const get = (type:string) => parts.find(part=>part.type===type)?.value||''
  return `${get('day')}.${get('month')}.${get('year')} ${get('hour')}:${get('minute')}`
}

export function uzbekDeadline(dateValue: string, timeValue: string): string {
  const dateMatch = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(dateValue.trim())
  const timeMatch = /^(\d{2}):(\d{2})$/.exec(timeValue.trim())
  if (!dateMatch || !timeMatch) throw new Error('Muddatni kk.oo.yyyy va ss:dd shaklida kiriting')
  const [, day, month, year] = dateMatch
  const [, hour, minute] = timeMatch
  const parsed = new Date(`${year}-${month}-${day}T${hour}:${minute}:00+05:00`)
  const exact = parsed.toLocaleString('sv-SE', { timeZone: 'Asia/Tashkent', hour12: false }).slice(0, 16)
  const entered = `${year}-${month}-${day} ${hour}:${minute}`
  if (Number.isNaN(parsed.getTime()) || exact !== entered) throw new Error('Muddat sanasi yoki vaqti noto‘g‘ri')
  return parsed.toISOString()
}
