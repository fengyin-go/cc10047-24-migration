import { createRouter, createWebHistory } from 'vue-router'

import Overview from '@/views/Overview.vue'
import SnapshotMigrationView from '@/views/SnapshotMigrationView.vue'
import WorkbenchView from '@/views/WorkbenchView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: Overview },
    // 固定路径必须先于 /:moduleKey 动态段注册。
    { path: '/snapshot-migration', name: 'snapshot-migration', component: SnapshotMigrationView },
    { path: '/:moduleKey', name: 'module', component: WorkbenchView, props: true },
  ],
})

export default router
