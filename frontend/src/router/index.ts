import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/Home.vue'),
    meta: { title: '首页' }
  },
  {
    path: '/onboarding',
    name: 'onboarding',
    component: () => import('@/views/Onboarding.vue'),
    meta: { title: '新世界引导' }
  },
  {
    path: '/reader/:projectId/:chapterNum?',
    name: 'reader',
    component: () => import('@/views/Reader.vue'),
    props: true,
    meta: { title: '章节阅读' }
  },
  {
    path: '/world/:projectId?',
    name: 'world',
    component: () => import('@/views/World.vue'),
    props: true,
    meta: { title: '世界管理' }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  }
})

export default router
