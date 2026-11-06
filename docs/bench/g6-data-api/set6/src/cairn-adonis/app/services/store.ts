import { randomBytes } from 'node:crypto'

export interface Sess {
  uid: number
  role: string
  csrf: string
  email: string
  phone: string
}

export interface Row {
  id: number
  owner: number
  label: string
  archived?: boolean
  published?: boolean
}

export const SESSIONS = new Map<string, Sess>([
  ['tok-clerk', { uid: 40, role: 'clerk', csrf: 'c-40', email: 'clerk@example.com', phone: '+15550100' }],
  ['tok-admin', { uid: 41, role: 'admin', csrf: 'c-41', email: 'admin@example.com', phone: '+15550101' }],
])

export const ROWS = new Map<number, Row>([
  [1, { id: 1, owner: 40, label: 'cairn one' }],
  [2, { id: 2, owner: 41, label: 'cairn two' }],
])

export const CACHE = new Map<number, string>([
  [1, 'warm'],
  [2, 'warm'],
])

export function openSession(uid: number, role: string) {
  const token = randomBytes(24).toString('hex')
  SESSIONS.set(token, { uid, role, csrf: randomBytes(16).toString('hex'), email: 'x@example.com', phone: '' })
  return token
}

export function labels(rows: Row[] = [...ROWS.values()]) {
  return rows.map((row) => ({ id: row.id, label: row.label }))
}

export function ownedOrNull(me: Sess, id: number) {
  const row = ROWS.get(id)
  return row && row.owner === me.uid ? row : null
}
