// 代码\前端\src\main.js —— 应用入口（第 9 阶段 T9）
// 装配 Vue 3 应用与 vue-router，挂载到 index.html 的 #app。
// 路由四条（四类页面）：/ask 提问、/answer/:answerId 答案与证据、/graph 图谱查看、/history 历史记录。

import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'

import App from './App.vue'
import AskView from './views/AskView.vue'
import AnswerView from './views/AnswerView.vue'
import GraphView from './views/GraphView.vue'
import HistoryView from './views/HistoryView.vue'

const routes = [
  { path: '/', redirect: '/ask' },
  { path: '/ask', name: 'ask', component: AskView },
  { path: '/answer/:answerId', name: 'answer', component: AnswerView, props: true },
  { path: '/graph', name: 'graph', component: GraphView },
  { path: '/history', name: 'history', component: HistoryView },
  // 兜底：未知路径回提问页
  { path: '/:pathMatch(.*)*', redirect: '/ask' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

createApp(App).use(router).mount('#app')
