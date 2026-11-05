import { randomBytes } from 'node:crypto'

export type Session = { uid: number; role: string; csrf: string; email: string; phone: string }
export type Row = { id: number; owner: number; label: string; approved?: boolean }
export type Env = { Variables: { user: Session } }

export const SESSIONS: Record<string, Session> = Object.assign(Object.create(null), {
  'tok-clerk': { uid: 40, role: 'clerk', csrf: 'c-40', email: 'clerk@example.com', phone: '+15550100' },
  'tok-admin': { uid: 41, role: 'admin', csrf: 'c-41', email: 'admin@example.com', phone: '+15550101' },
})
export const ROWS: Record<string, Row> = Object.assign(Object.create(null), {
  '1': { id: 1, owner: 40, label: 'atlas one' },
  '2': { id: 2, owner: 41, label: 'atlas two' },
})
export const CACHE: Record<string, string> = Object.assign(Object.create(null), { '1': 'warm', '2': 'warm' })

export function openSession(uid: number, role: string): string {
  const token = randomBytes(24).toString('hex')
  SESSIONS[token] = { uid, role, csrf: randomBytes(16).toString('hex'), email: 'x@example.com', phone: '' }
  return token
}
