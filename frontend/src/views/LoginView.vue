<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NCard, NForm, NFormItem, NInput, NButton, NText,
} from 'naive-ui'
import { useMessage } from 'naive-ui'
import * as authApi from '@/api/auth'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const message = useMessage()
const auth = useAuthStore()

function goAfterLogin() {
  const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : ''
  router.replace(redirect && redirect.startsWith('/') ? redirect : '/chat')
}

type Mode = 'login' | 'register' | 'changePwd'
const mode = ref<Mode>('login')
const loading = ref(false)

// ---- login ----
const account = ref('')
const password = ref('')

// ---- register ----
const regPhone = ref('')
const regPassword = ref('')
const regPassword2 = ref('')

// ---- change password ----
const cpPhone = ref('')
const cpNewPassword = ref('')

const PHONE_RE = /^1[3-9]\d{9}$/

async function doLogin() {
  if (!account.value.trim()) { message.warning('请输入账号（手机号）'); return }
  if (!password.value) { message.warning('请输入密码'); return }
  loading.value = true
  try {
    const res = await authApi.login(account.value.trim(), password.value)
    if (res.token) {
      auth.setAuth(res.token, res.phone)
      message.success('登录成功')
      goAfterLogin()
    }
  } catch (e) {
    message.error((e as Error).message || '登录失败')
  } finally {
    loading.value = false
  }
}

async function doRegister() {
  const phone = regPhone.value.trim()
  if (!PHONE_RE.test(phone)) { message.warning('请输入正确的手机号'); return }
  if (regPassword.value.length < 6) { message.warning('密码长度至少 6 位'); return }
  if (regPassword.value !== regPassword2.value) { message.warning('两次输入的密码不一致'); return }
  loading.value = true
  try {
    const res = await authApi.register(phone, regPassword.value)
    if (res.token) {
      auth.setAuth(res.token, res.phone)
      message.success('注册成功，已自动登录')
      goAfterLogin()
    }
  } catch (e) {
    message.error((e as Error).message || '注册失败')
  } finally {
    loading.value = false
  }
}

async function doChangePwd() {
  const phone = cpPhone.value.trim()
  if (!PHONE_RE.test(phone)) { message.warning('请输入正确的手机号'); return }
  if (cpNewPassword.value.length < 6) { message.warning('新密码长度至少 6 位'); return }
  loading.value = true
  try {
    await authApi.changePassword(phone, cpNewPassword.value)
    message.success('密码修改成功，请使用新密码登录')
    mode.value = 'login'
    account.value = phone
    password.value = ''
  } catch (e) {
    // 后端会校验数据库中是否存在该手机号
    message.error((e as Error).message || '修改密码失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-panel">
      <div class="brand">
        <div class="brand-logo">smallhouse</div>
        <div class="brand-title">个人知识小助手</div>
        <div class="brand-sub">多模型 · RAG · 飞书同步</div>
      </div>

      <!-- 登录卡片 -->
      <n-card v-if="mode === 'login'" class="auth-card" :bordered="false">
        <template #header>账号登录</template>
        <n-form @keyup.enter="doLogin">
          <n-form-item label="账号" label-placement="top">
            <n-input v-model:value="account" placeholder="请输入手机号" :input-props="{ autocomplete: 'username' }" />
          </n-form-item>
          <n-form-item label="密码" label-placement="top">
            <n-input
              v-model:value="password" type="password" show-password-on="click"
              placeholder="请输入密码" :input-props="{ autocomplete: 'current-password' }"
            />
          </n-form-item>
          <n-button type="primary" block :loading="loading" @click="doLogin">登 录</n-button>
        </n-form>
        <div class="card-footer">
          <n-button quaternary size="small" @click="mode = 'changePwd'">忘记密码？</n-button>
          <!-- 右下角注册按钮 -->
          <n-button quaternary size="small" type="primary" @click="mode = 'register'; regPhone = ''; regPassword = ''; regPassword2 = ''">注 册</n-button>
        </div>
      </n-card>

      <!-- 注册卡片 -->
      <n-card v-else-if="mode === 'register'" class="auth-card" :bordered="false">
        <template #header>注册账号</template>
        <n-form @keyup.enter="doRegister">
          <n-form-item label="手机号" label-placement="top">
            <n-input v-model:value="regPhone" placeholder="请输入手机号" maxlength="11" />
          </n-form-item>
          <n-form-item label="密码" label-placement="top">
            <n-input v-model:value="regPassword" type="password" show-password-on="click" placeholder="至少 6 位" />
          </n-form-item>
          <n-form-item label="确认密码" label-placement="top">
            <n-input v-model:value="regPassword2" type="password" show-password-on="click" placeholder="再次输入密码" />
          </n-form-item>
          <n-button type="primary" block :loading="loading" @click="doRegister">注 册</n-button>
        </n-form>
        <div class="card-footer">
          <n-button quaternary size="small" @click="mode = 'login'">返回登录</n-button>
        </div>
      </n-card>

      <!-- 修改密码卡片 -->
      <n-card v-else class="auth-card" :bordered="false">
        <template #header>修改密码</template>
        <n-text depth="3" style="font-size: 12px; display: block; margin-bottom: 12px">
          将校验数据库中是否存在该手机号，存在则更新密码
        </n-text>
        <n-form @keyup.enter="doChangePwd">
          <n-form-item label="手机号" label-placement="top">
            <n-input v-model:value="cpPhone" placeholder="请输入注册时的手机号" maxlength="11" />
          </n-form-item>
          <n-form-item label="新密码" label-placement="top">
            <n-input v-model:value="cpNewPassword" type="password" show-password-on="click" placeholder="至少 6 位" />
          </n-form-item>
          <n-button type="primary" block :loading="loading" @click="doChangePwd">确认修改</n-button>
        </n-form>
        <div class="card-footer">
          <n-button quaternary size="small" @click="mode = 'login'">返回登录</n-button>
        </div>
      </n-card>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  /* 跟随项目主题（--bg-app 由 html.light / dark 切换） */
  background:
    radial-gradient(1200px 600px at 85% -10%, rgba(59, 130, 246, 0.08), transparent 60%),
    radial-gradient(900px 500px at -10% 110%, rgba(59, 130, 246, 0.06), transparent 60%),
    var(--bg-app);
  color: var(--text-primary);
  padding: 24px;
  transition: background-color 0.2s ease, color 0.2s ease;
}
.login-panel {
  display: flex;
  align-items: center;
  gap: 56px;
  flex-wrap: wrap;
  justify-content: center;
}
.brand {
  max-width: 320px;
}
.brand-logo {
  font-size: 44px;
  font-weight: 800;
  letter-spacing: 2px;
  margin-bottom: 12px;
  color: #3b82f6;
}
.brand-title {
  font-size: 26px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--text-primary);
}
.brand-sub {
  font-size: 14px;
  color: var(--text-secondary);
}
.auth-card {
  width: 380px;
  border-radius: 16px;
  background: var(--bg-elevated);
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.08);
}
/* 输入框与按钮圆角 */
.auth-card :deep(.n-input) {
  border-radius: 10px;
}
.auth-card :deep(.n-button) {
  border-radius: 10px;
}
.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
}
</style>
