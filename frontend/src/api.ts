export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const storage = typeof localStorage !== 'undefined' && typeof localStorage.getItem === 'function'
  ? localStorage : null
let token = storage?.getItem('raqobat_token') || ''

export class ApiError extends Error {
  status?: number
  constructor(message: string, status?: number) { super(message); this.status = status }
}

type ApiOptions = RequestInit & { timeoutMs?: number }

export function setToken(value: string) {
  token = value
  if (value) storage?.setItem('raqobat_token', value)
  else storage?.removeItem('raqobat_token')
}

export async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (options.body && !(options.body instanceof FormData) && !(options.body instanceof URLSearchParams) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const controller = new AbortController()
  let timedOut = false
  const upstreamSignal = options.signal
  const abortFromUpstream = () => controller.abort()
  upstreamSignal?.addEventListener('abort', abortFromUpstream, { once: true })
  const timeout = window.setTimeout(() => { timedOut = true; controller.abort() }, options.timeoutMs ?? 15_000)
  const { timeoutMs: _timeoutMs, ...fetchOptions } = options
  let response!: Response
  const isReadOnly = (options.method || 'GET').toUpperCase() === 'GET'
  try {
    for (let attempt = 0; attempt < (isReadOnly ? 2 : 1); attempt += 1) {
      try {
        response = await fetch(`${API_URL}${path}`, { ...fetchOptions, headers, signal: controller.signal })
        break
      } catch (error) {
        if ((error as Error).name === 'AbortError') {
          throw new ApiError(timedOut ? 'Server belgilangan vaqtda javob bermadi. Qayta urinib ko‘ring.' : 'So‘rov bekor qilindi.')
        }
        if (attempt === 0 && isReadOnly) continue
        throw new ApiError('Backend bilan aloqa o‘rnatilmadi. Backend va ma’lumotlar bazasi ishlayotganini tekshiring.')
      }
    }
  } finally {
    window.clearTimeout(timeout)
    upstreamSignal?.removeEventListener('abort', abortFromUpstream)
  }
  if (response.status === 401) {
    setToken('')
    window.dispatchEvent(new Event('raqobat:logout'))
  }
  if (!response.ok) {
    let message = 'So‘rovni bajarib bo‘lmadi'
    try { message = (await response.json()).detail || message } catch { /* javob JSON emas */ }
    throw new ApiError(message, response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export async function download(path: string, filename: string) {
  const headers = new Headers()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(`${API_URL}${path}`, { headers })
  if (!response.ok) throw new Error('Faylni yuklab bo‘lmadi')
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url; link.download = filename; link.click()
  URL.revokeObjectURL(url)
}
