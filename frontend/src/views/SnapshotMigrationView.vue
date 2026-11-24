<template>
  <section class="page" data-module="snapshot-migration">
    <header class="page-head">
      <div>
        <h2>快照字段迁移</h2>
        <p class="page-desc">
          历史快照金额字段 amount_cents → amount_decimal：登记上线依赖与数据库兼容范围、
          生产环境重演、迁移确认、双格式读取。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" data-testid="open-register" type="button" @click="openRegister">
          登记迁移记录
        </button>
        <button class="btn" data-testid="reload" type="button" @click="reload">刷新</button>
      </div>
    </header>

    <div class="stat-row">
      <article class="stat-card">
        <span class="stat-label">迁移记录</span>
        <strong class="stat-value">{{ rows.length }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">待确认</span>
        <strong class="stat-value">{{ rows.filter((r) => r.status === '待确认').length }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">已发布</span>
        <strong class="stat-value">{{ rows.filter((r) => r.status === '已发布').length }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">待处理更正</span>
        <strong class="stat-value">{{ pendingCorrectionCount }}</strong>
      </article>
    </div>

    <h3 class="section-title">快照字段迁移记录</h3>
    <table class="data-table">
      <thead>
        <tr>
          <th>迁移标识</th>
          <th>快照标识</th>
          <th>目标湖表</th>
          <th>原值（分）</th>
          <th>候选新值（分）</th>
          <th>本次允许采用（元）</th>
          <th>换算版本</th>
          <th>更正次数</th>
          <th>状态</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="row.id"
          :data-testid="`migration-${row.id}`"
          :data-status="row.status"
        >
          <td>{{ row.迁移标识 }}</td>
          <td>{{ row.快照标识 }}</td>
          <td>{{ row.目标湖表 }}</td>
          <td>{{ row.原值分 }}</td>
          <td>{{ row.候选新值分 ?? '—' }}</td>
          <td>{{ row.本次允许采用元 }}</td>
          <td>{{ row.换算版本 }}</td>
          <td>{{ row.更正次数 }}</td>
          <td>{{ row.status }}{{ row.已暂停确认 ? '（已暂停确认）' : '' }}</td>
          <td class="row-actions">
            <button class="link" type="button" :data-testid="`detail-${row.id}`" @click="select(row)">
              详情
            </button>
            <button class="link" type="button" :data-testid="`replay-${row.id}`" @click="doReplay(row)">
              重演
            </button>
            <button
              v-if="row.status === '待确认' && !row.已暂停确认"
              class="link"
              type="button"
              :data-testid="`pause-${row.id}`"
              @click="doPause(row)"
            >
              暂停确认
            </button>
            <button
              v-if="row.已暂停确认"
              class="link"
              type="button"
              :data-testid="`resume-${row.id}`"
              @click="doResume(row)"
            >
              恢复确认
            </button>
            <button class="link" type="button" :data-testid="`correct-${row.id}`" @click="openCorrection(row)">
              补报更正
            </button>
            <button
              v-if="row.status === '待确认' && !row.已暂停确认"
              class="link"
              type="button"
              :data-testid="`confirm-${row.id}`"
              @click="doConfirm(row)"
            >
              迁移确认
            </button>
            <button class="link" type="button" :data-testid="`read-cents-${row.id}`" @click="doRead(row, 'cents')">
              读原快照
            </button>
            <button class="link" type="button" :data-testid="`read-decimal-${row.id}`" @click="doRead(row, 'decimal')">
              读元格式
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td colspan="10" class="empty-state">暂无迁移记录，可先登记迁移记录</td>
        </tr>
      </tbody>
    </table>

    <section v-if="selected" class="detail-panel" data-testid="migration-detail">
      <h3 class="section-title">
        快照详情：{{ selected.快照标识 }}（{{ selected.迁移标识 }}）
      </h3>
      <div class="amount-row">
        <article class="amount-card">
          <span class="stat-label">原值</span>
          <strong class="stat-value" data-testid="detail-original">{{ selected.原值分 }} 分 / {{ selected.原值元 }} 元</strong>
        </article>
        <article class="amount-card">
          <span class="stat-label">候选新值</span>
          <strong class="stat-value" data-testid="detail-candidate">
            {{ selected.候选新值分 != null ? `${selected.候选新值分} 分 / ${selected.候选新值元} 元` : '—' }}
          </strong>
        </article>
        <article class="amount-card">
          <span class="stat-label">本次允许采用的金额</span>
          <strong class="stat-value" data-testid="detail-adopted">{{ selected.本次允许采用元 }} 元</strong>
        </article>
        <article class="amount-card">
          <span class="stat-label">已发布口径</span>
          <strong class="stat-value" data-testid="detail-published">
            {{ selected.已发布元 != null ? `${selected.已发布元} 元（${selected.换算版本}）` : '未发布' }}
          </strong>
        </article>
      </div>
      <dl class="fact-grid">
        <dt>上线依赖</dt>
        <dd data-testid="detail-deps">{{ selected.上线依赖 }}</dd>
        <dt>数据库兼容范围</dt>
        <dd data-testid="detail-compat">{{ selected.数据库兼容范围 }}</dd>
        <dt>换算规则</dt>
        <dd>{{ selected.换算规则 }}</dd>
        <dt>确认单号 / 时间</dt>
        <dd>{{ selected.确认单号 ?? '—' }} / {{ selected.确认时间 ?? '—' }}</dd>
      </dl>

      <h4 class="section-subtitle">重演证据（生产预演，共 {{ selected.重演次数 }} 次）</h4>
      <table class="data-table">
        <thead>
          <tr>
            <th>重演序号</th>
            <th>环境</th>
            <th>原值分</th>
            <th>换算后元</th>
            <th>换算版本</th>
            <th>重演时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="ev in selected.重演证据" :key="ev.重演序号">
            <td>{{ ev.重演序号 }}</td>
            <td>{{ ev.环境 }}</td>
            <td>{{ ev.原值分 }}</td>
            <td>{{ ev.换算后元 }}</td>
            <td>{{ ev.换算版本 }}</td>
            <td>{{ ev.重演时间 }}</td>
          </tr>
          <tr v-if="!selected.重演证据.length">
            <td colspan="6" class="empty-state">尚未重演</td>
          </tr>
        </tbody>
      </table>

      <h4 class="section-subtitle">更正记录（原值与更正来源留存）</h4>
      <table class="data-table">
        <thead>
          <tr>
            <th>更正标识</th>
            <th>原值分</th>
            <th>更正值分</th>
            <th>换算后元</th>
            <th>更正来源</th>
            <th>状态</th>
            <th>补报时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="corr in selected.更正记录" :key="corr.id">
            <td>{{ corr.更正标识 }}</td>
            <td>{{ corr.原值分 }}</td>
            <td>{{ corr.更正值分 }}</td>
            <td>{{ corr.换算后元 }}</td>
            <td>{{ corr.更正来源 }}</td>
            <td>{{ corr.status }}</td>
            <td>{{ corr.补报时间 }}</td>
          </tr>
          <tr v-if="!selected.更正记录.length">
            <td colspan="7" class="empty-state">暂无更正</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="readResult" class="read-result" data-testid="read-result">
      <h3 class="section-title">读取结果</h3>
      <p v-if="readResult.ok" class="read-line">
        {{ readResult.快照标识 }} · {{ readResult.读取口径 }}：
        <strong v-if="readResult.format === 'cents'">{{ readResult.amount_cents }} 分</strong>
        <strong v-else>{{ readResult.amount_decimal }} 元（换算版本 {{ readResult.换算版本 }}）</strong>
      </p>
      <p v-else class="error-text">{{ readResult.message }}</p>
    </section>

    <h3 class="section-title">快照审计清单（迁移确认结果）</h3>
    <table class="data-table" data-testid="audit-checklist">
      <thead>
        <tr>
          <th>迁移标识</th>
          <th>快照标识</th>
          <th>原值（元）</th>
          <th>候选新值（元）</th>
          <th>本次采用（元）</th>
          <th>换算版本</th>
          <th>确认结果</th>
          <th>更正次数</th>
          <th>同步时间</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="entry in auditItems" :key="entry.id">
          <td>{{ entry.迁移标识 }}</td>
          <td>{{ entry.快照标识 }}</td>
          <td>{{ entry.原值元 }}</td>
          <td>{{ entry.候选新值元 ?? '—' }}</td>
          <td>{{ entry.本次采用元 }}</td>
          <td>{{ entry.换算版本 }}</td>
          <td>{{ entry.确认结果 }}</td>
          <td>{{ entry.更正次数 }}</td>
          <td>{{ entry.同步时间 }}</td>
        </tr>
        <tr v-if="!auditItems.length">
          <td colspan="9" class="empty-state">暂无审计记录，迁移确认后自动同步</td>
        </tr>
      </tbody>
    </table>

    <div class="page-head">
      <h3 class="section-title">更正查询（原值 / 换算版本 / 待处理更正）</h3>
      <div class="page-actions">
        <button
          v-for="option in correctionFilters"
          :key="option.label"
          class="btn"
          :class="{ primary: correctionFilter === option.value }"
          type="button"
          :data-testid="`corr-filter-${option.label}`"
          @click="setCorrectionFilter(option.value)"
        >
          {{ option.label }}
        </button>
      </div>
    </div>
    <table class="data-table" data-testid="correction-list">
      <thead>
        <tr>
          <th>更正标识</th>
          <th>快照标识</th>
          <th>原值分</th>
          <th>更正值分</th>
          <th>换算后元</th>
          <th>更正来源</th>
          <th>换算版本</th>
          <th>状态</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="corr in corrections" :key="corr.id">
          <td>{{ corr.更正标识 }}</td>
          <td>{{ corr.快照标识 }}</td>
          <td>{{ corr.原值分 }}</td>
          <td>{{ corr.更正值分 }}</td>
          <td>{{ corr.换算后元 }}</td>
          <td>{{ corr.更正来源 }}</td>
          <td>{{ corr.换算版本 ?? '—' }}</td>
          <td>{{ corr.status }}</td>
        </tr>
        <tr v-if="!corrections.length">
          <td colspan="8" class="empty-state">暂无更正记录</td>
        </tr>
      </tbody>
    </table>

    <div v-if="showRegister" class="modal-backdrop" data-testid="register-modal">
      <form class="modal" @submit.prevent="submitRegister">
        <h3>登记迁移记录</h3>
        <label class="create-field">
          <span>快照标识</span>
          <input v-model="registerForm.snapshot_key" data-testid="register-snapshot" required />
        </label>
        <label class="create-field">
          <span>目标湖表</span>
          <input v-model="registerForm.table" data-testid="register-table" required />
        </label>
        <label class="create-field">
          <span>原值（分）</span>
          <input v-model="registerForm.amount_cents" data-testid="register-cents" required type="number" min="0" />
        </label>
        <label class="create-field">
          <span>上线依赖</span>
          <input v-model="registerForm.deploy_deps" data-testid="register-deps" required placeholder="reader-sdk>=2.3.0" />
        </label>
        <label class="create-field">
          <span>数据库兼容范围</span>
          <input v-model="registerForm.db_compat" data-testid="register-compat" required placeholder="delta-lake>=2.4,<3.0" />
        </label>
        <div class="page-actions">
          <button class="btn" type="button" @click="showRegister = false">取消</button>
          <button class="btn primary" data-testid="submit-register" type="submit" :disabled="submitting">
            {{ submitting ? '提交中…' : '确认登记' }}
          </button>
        </div>
      </form>
    </div>

    <div v-if="correctionTarget" class="modal-backdrop" data-testid="correction-modal">
      <form class="modal" @submit.prevent="submitCorrectionForm">
        <h3>补报更正：{{ correctionTarget.快照标识 }}（原值 {{ correctionTarget.原值分 }} 分）</h3>
        <label class="create-field">
          <span>更正值（分）</span>
          <input v-model="correctionForm.corrected_cents" data-testid="correction-cents" required type="number" min="0" />
        </label>
        <label class="create-field">
          <span>更正来源</span>
          <input v-model="correctionForm.source" data-testid="correction-source" required placeholder="原来源系统" />
        </label>
        <label class="create-field">
          <span>更正标识（可选，用于幂等去重）</span>
          <input v-model="correctionForm.correction_key" data-testid="correction-key" placeholder="留空按内容自动生成" />
        </label>
        <div class="page-actions">
          <button class="btn" type="button" @click="correctionTarget = null">取消</button>
          <button class="btn primary" data-testid="submit-correction" type="submit" :disabled="submitting">
            {{ submitting ? '提交中…' : '确认补报' }}
          </button>
        </div>
      </form>
    </div>

    <footer class="page-foot">
      <span>共 {{ rows.length }} 条迁移记录</span>
      <span v-if="message" class="ok-text" data-testid="action-message">{{ message }}</span>
      <span v-if="errorMessage" class="error-text" data-testid="action-error">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  confirmMigration,
  getMigration,
  listAuditChecklist,
  listCorrections,
  listMigrations,
  pauseMigration,
  readSnapshot,
  registerMigration,
  replayMigration,
  resumeMigration,
  submitCorrection,
} from '@/api/snapshot-migration'
import type {
  AuditEntry,
  CorrectionRow,
  MigrationResult,
  MigrationRow,
  ReadResult,
} from '@/api/snapshot-migration'

const rows = ref<MigrationRow[]>([])
const auditItems = ref<AuditEntry[]>([])
const corrections = ref<CorrectionRow[]>([])
const pendingCorrectionCount = ref(0)
const selected = ref<MigrationRow | null>(null)
const readResult = ref<ReadResult | null>(null)
const message = ref('')
const errorMessage = ref('')
const submitting = ref(false)
const showRegister = ref(false)
const correctionTarget = ref<MigrationRow | null>(null)
const correctionFilter = ref('')
const correctionFilters = [
  { label: '全部', value: '' },
  { label: '待处理', value: '待处理' },
  { label: '已采用', value: '已采用' },
]
const registerForm = ref({
  snapshot_key: '',
  table: '',
  amount_cents: 0,
  deploy_deps: '',
  db_compat: '',
})
const correctionForm = ref({
  corrected_cents: 0,
  source: '',
  correction_key: '',
})

const canAct = computed(() => !submitting.value)

async function reload() {
  errorMessage.value = ''
  try {
    const [migrationData, auditData, correctionData] = await Promise.all([
      listMigrations(),
      listAuditChecklist(),
      listCorrections(correctionFilter.value || undefined),
    ])
    rows.value = migrationData.items
    auditItems.value = auditData.items
    corrections.value = correctionData.items
    pendingCorrectionCount.value = correctionData.待处理数
    if (selected.value) {
      const fresh = await getMigration(selected.value.id)
      if (fresh.ok && fresh.migration) selected.value = fresh.migration
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '迁移数据读取失败'
  }
}

function handleResult(result: MigrationResult, successFallback?: string) {
  if (result.ok) {
    message.value = result.message || successFallback || '操作完成'
    errorMessage.value = ''
  } else {
    errorMessage.value = result.message || '操作失败'
    message.value = ''
  }
}

function select(row: MigrationRow) {
  selected.value = row
}

async function run(action: () => Promise<MigrationResult>) {
  if (!canAct.value) return
  submitting.value = true
  try {
    handleResult(await action())
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '操作失败'
  } finally {
    submitting.value = false
    await reload()
  }
}

function doReplay(row: MigrationRow) {
  void run(() => replayMigration(row.id))
}

function doPause(row: MigrationRow) {
  void run(() => pauseMigration(row.id))
}

function doResume(row: MigrationRow) {
  void run(() => resumeMigration(row.id))
}

function doConfirm(row: MigrationRow) {
  void run(() => confirmMigration(row.id))
}

async function doRead(row: MigrationRow, format: 'cents' | 'decimal') {
  readResult.value = await readSnapshot(row.id, format)
  if (!readResult.value.ok) {
    errorMessage.value = readResult.value.message ?? '读取失败'
    message.value = ''
  } else {
    errorMessage.value = ''
  }
}

function openRegister() {
  registerForm.value = { snapshot_key: '', table: '', amount_cents: 0, deploy_deps: '', db_compat: '' }
  showRegister.value = true
}

async function submitRegister() {
  submitting.value = true
  try {
    const result = await registerMigration({
      snapshot_key: registerForm.value.snapshot_key,
      table: registerForm.value.table,
      amount_cents: Number(registerForm.value.amount_cents),
      deploy_deps: registerForm.value.deploy_deps,
      db_compat: registerForm.value.db_compat,
    })
    handleResult(result)
    if (result.ok) showRegister.value = false
  } finally {
    submitting.value = false
    await reload()
  }
}

function openCorrection(row: MigrationRow) {
  correctionTarget.value = row
  correctionForm.value = { corrected_cents: 0, source: '', correction_key: '' }
}

async function submitCorrectionForm() {
  if (!correctionTarget.value) return
  submitting.value = true
  try {
    const result = await submitCorrection(correctionTarget.value.id, {
      corrected_cents: Number(correctionForm.value.corrected_cents),
      source: correctionForm.value.source,
      correction_key: correctionForm.value.correction_key || undefined,
    })
    if (result.ok) {
      message.value = result.deduplicated ? `${result.message}` : result.message
      errorMessage.value = ''
      correctionTarget.value = null
    } else {
      errorMessage.value = result.message
    }
  } finally {
    submitting.value = false
    await reload()
  }
}

async function setCorrectionFilter(value: string) {
  correctionFilter.value = value
  const data = await listCorrections(value || undefined)
  corrections.value = data.items
  pendingCorrectionCount.value = data.待处理数
}

onMounted(reload)
</script>

<style scoped>
.section-title {
  font-size: 14px;
  margin: 16px 0 8px;
}
.section-subtitle {
  font-size: 13px;
  margin: 12px 0 6px;
  color: var(--muted);
}
.detail-panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  margin-top: 12px;
}
.amount-row {
  display: flex;
  gap: 12px;
  margin-bottom: 8px;
}
.amount-card {
  flex: 1;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  background: #fafbfc;
}
.amount-card .stat-value {
  font-size: 15px;
}
.fact-grid {
  display: grid;
  grid-template-columns: 140px 1fr;
  gap: 4px 12px;
  margin: 8px 0;
  font-size: 13px;
}
.fact-grid dt {
  color: var(--muted);
}
.fact-grid dd {
  margin: 0;
}
.read-result {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  margin-top: 12px;
}
.read-line {
  margin: 0;
  font-size: 14px;
}
.ok-text {
  color: #15803d;
}
</style>
