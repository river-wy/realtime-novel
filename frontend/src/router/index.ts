import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/Home.vue'),
    meta: { title: '首页' }
  },
  {
    path: '/chat',
    name: 'chat',
    component: () => import('@/views/Chat.vue'),
    meta: { title: '管家对话' }
  },
  {
    path: '/reader/:projectId/:chapterNum?',
    name: 'reader',
    component: () => import('@/views/Reader.vue'),
    props: true,
    meta: { title: '阅读' }
  },
  {
    path: '/world/:projectId?',
    name: 'world',
    component: () => import('@/views/World.vue'),
    props: true,
    meta: { title: '世界' }
  },
  {
    path: '/worlds',
    name: 'world-list',
    component: () => import('@/views/WorldList.vue'),
    meta: { title: '我的世界' }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  }
})

router.afterEach((to) => {
  const sub = (to.meta?.title as string) || ''
  document.title = sub ? `${sub} · 小说 · 世界` : '小说 · 世界'
})

export default router
