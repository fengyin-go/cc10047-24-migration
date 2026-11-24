/** 快照字段迁移接口封装：历史快照 amount_cents → amount_decimal。 */
import { request } from './client'

export type ReplayEvidence = {
  重演序号: number
  环境: string
  快照标识: string
  目标湖表: string
  原值分: number
  换算后元: string
  换算版本: string
  重演时间: string
}

export type CorrectionRow = {
  id: number
  更正标识: string
  迁移标识: string
  快照标识: string
  原值分: number
  原值元: string
  更正值分: number
  换算后元: string
  更正来源: string
  status: string
  补报时间: string
  采用时间: string | null
  换算版本?: string | null
}

export type MigrationRow = {
  id: number
  迁移标识: string
  快照标识: string
  目标湖表: string
  源字段: string
  目标字段: string
  原值分: number
  原值元: string
  候选新值分: number | null
  候选新值元: string | null
  本次允许采用分: number
  本次允许采用元: string
  已发布分: number | null
  已发布元: string | null
  初始换算版本: string
  换算版本: string
  换算规则: string
  上线依赖: string
  数据库兼容范围: string
  status: string
  已暂停确认: boolean
  更正次数: number
  待处理更正数: number
  重演次数: number
  重演证据: ReplayEvidence[]
  更正记录: CorrectionRow[]
  确认单号: string | null
  确认时间: string | null
}

export type AuditEntry = {
  id: number
  迁移标识: string
  快照标识: string
  目标湖表: string
  原值分: number
  原值元: string
  候选新值分: number | null
  候选新值元: string | null
  本次采用分: number
  本次采用元: string
  换算版本: string
  确认结果: string
  更正次数: number
  确认单号: string | null
  同步时间: string
}

export type MigrationListResult = { ok: boolean; items: MigrationRow[]; total: number }
export type MigrationResult = {
  ok: boolean
  message: string
  migration?: MigrationRow
  idempotent?: boolean
  audit_entry?: AuditEntry
}
export type CorrectionResult = {
  ok: boolean
  message: string
  deduplicated?: boolean
  correction?: CorrectionRow
  migration?: MigrationRow
}
export type AuditListResult = { ok: boolean; items: AuditEntry[]; total: number }
export type CorrectionListResult = {
  ok: boolean
  items: CorrectionRow[]
  total: number
  待处理数: number
}
export type ReadResult = {
  ok: boolean
  message?: string
  format?: string
  快照标识?: string
  amount_cents?: number
  amount_decimal?: string
  换算版本?: string
  读取口径?: string
}

async function getJson<T>(path: string): Promise<T> {
  const response = await request(path)
  return (await response.json()) as T
}

async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const response = await request(path, {
    method: 'POST',
    body: JSON.stringify(body ?? {}),
  })
  return (await response.json()) as T
}

export function listMigrations(): Promise<MigrationListResult> {
  return getJson('/api/snapshot-migrations')
}

export function getMigration(id: number): Promise<MigrationResult> {
  return getJson(`/api/snapshot-migrations/${id}`)
}

export function registerMigration(payload: {
  snapshot_key: string
  table: string
  amount_cents: number
  deploy_deps: string
  db_compat: string
}): Promise<MigrationResult> {
  return postJson('/api/snapshot-migrations', payload)
}

export function replayMigration(id: number): Promise<MigrationResult> {
  return postJson(`/api/snapshot-migrations/${id}/replay`)
}

export function pauseMigration(id: number): Promise<MigrationResult> {
  return postJson(`/api/snapshot-migrations/${id}/pause`)
}

export function resumeMigration(id: number): Promise<MigrationResult> {
  return postJson(`/api/snapshot-migrations/${id}/resume`)
}

export function confirmMigration(id: number): Promise<MigrationResult> {
  return postJson(`/api/snapshot-migrations/${id}/confirm`, {})
}

export function submitCorrection(
  id: number,
  payload: { corrected_cents: number; source: string; correction_key?: string },
): Promise<CorrectionResult> {
  return postJson(`/api/snapshot-migrations/${id}/corrections`, payload)
}

export function readSnapshot(id: number, format: 'cents' | 'decimal'): Promise<ReadResult> {
  return getJson(`/api/snapshot-migrations/${id}/read?format=${format}`)
}

export function listAuditChecklist(): Promise<AuditListResult> {
  return getJson('/api/snapshot-migrations/audit-checklist')
}

export function listCorrections(status?: string): Promise<CorrectionListResult> {
  const query = status ? `?status=${encodeURIComponent(status)}` : ''
  return getJson(`/api/snapshot-migrations/corrections${query}`)
}
