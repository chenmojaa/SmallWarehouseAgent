<script setup lang="ts">
import { ref } from 'vue'
import { t } from '@/i18n'
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

// ---- change password (now requires old_password, per P0 hardening) ----
const cpPhone = ref('')
const cpOldPassword = ref('')
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
  if (!cpOldPassword.value) { message.warning('请输入旧密码以验证身份'); return }
  if (cpNewPassword.value.length < 6) { message.warning('新密码长度至少 6 位'); return }
  if (cpOldPassword.value === cpNewPassword.value) { message.warning('新密码不能与旧密码相同'); return }
  loading.value = true
  try {
    await authApi.changePassword(phone, cpOldPassword.value, cpNewPassword.value)
    message.success('密码修改成功，请使用新密码登录')
    mode.value = 'login'
    account.value = phone
    password.value = ''
    cpOldPassword.value = ''
    cpNewPassword.value = ''
  } catch (e) {
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
        <img src="/logo.png" alt="Small Warehouse Agent" class="brand-logo-img" />
        <div class="brand-title">{{ t('app.subtitle', '个人知识小助理', 'Personal Knowledge Assistant') }}</div>
        <div class="brand-sub">{{ t('app.brand.tagline', '多模型 · RAG · 飞书同步', 'Multi-LLM · RAG · Feishu Sync') }}</div>
      </div>

      <!-- 登录卡片 -->
      <n-card v-if="mode === 'login'" class="auth-card" :bordered="false">
        <template #header>{{ t('auth.login.title', '账号登录', 'Account Login') }}</template>
        <n-form @keyup.enter="doLogin">
          <n-form-item :label="t('auth.login.account', '账号', 'Account')" label-placement="top">
            <n-input v-model:value="account" :placeholder="t('auth.login.placeholder.account', '请输入手机号', 'Enter phone number')" :input-props="{ autocomplete: 'username' }" />
          </n-form-item>
          <n-form-item :label="t('auth.login.password', '密码', 'Password')" label-placement="top">
            <n-input
              v-model:value="password" type="password" show-password-on="click"
              :placeholder="t('auth.login.placeholder.password', '请输入密码', 'Enter password')" :input-props="{ autocomplete: 'current-password' }"
            />
          </n-form-item>
          <n-button type="primary" block :loading="loading" @click="doLogin">{{ t('auth.login.submit', '登 录', 'Log In') }}</n-button>
        </n-form>
        <div class="card-footer">
          <n-button quaternary size="small" @click="mode = 'changePwd'">{{ t('auth.login.forgot', '忘记密码？', 'Forgot password?') }}</n-button>
          <!-- 右下角注册按钮 -->
          <n-button quaternary size="small" type="primary" @click="mode = 'register'; regPhone = ''; regPassword = ''; regPassword2 = ''">{{ t('auth.login.toRegister', '注 册', 'Sign Up') }}</n-button>
        </div>
      </n-card>

      <!-- 注册卡片 -->
      <n-card v-else-if="mode === 'register'" class="auth-card" :bordered="false">
        <template #header>{{ t('auth.register.title', '注册账号', 'Create Account') }}</template>
        <n-form @keyup.enter="doRegister">
          <n-form-item :label="t('auth.register.phone', '手机号', 'Phone')" label-placement="top">
            <n-input v-model:value="regPhone" :placeholder="t('auth.login.placeholder.account', '请输入手机号', 'Enter phone number')" maxlength="11" />
          </n-form-item>
          <n-form-item :label="t('auth.login.password', '密码', 'Password')" label-placement="top">
            <n-input v-model:value="regPassword" type="password" show-password-on="click" :placeholder="t('auth.register.placeholder.password', '至少 6 位', 'At least 6 chars')" />
          </n-form-item>
          <n-form-item :label="t('auth.register.password2', '确认密码', 'Confirm Password')" label-placement="top">
            <n-input v-model:value="regPassword2" type="password" show-password-on="click" :placeholder="t('auth.register.placeholder.password2', '再次输入密码', 'Re-enter password')" />
          </n-form-item>
          <n-button type="primary" block :loading="loading" @click="doRegister">{{ t('auth.login.toRegister', '注 册', 'Sign Up') }}</n-button>
        </n-form>
        <div class="card-footer">
          <n-button quaternary size="small" @click="mode = 'login'">{{ t('auth.backToLogin', '返回登录', 'Back to login') }}</n-button>
        </div>
      </n-card>

      <!-- 修改密码卡片（P0: now requires old password） -->
      <n-card v-else class="auth-card" :bordered="false">
        <template #header>{{ t('auth.change.title', '修改密码', 'Change Password') }}</template>
        <n-text depth="3" style="font-size: 12px; display: block; margin-bottom: 12px">
          输入手机号 + 旧密码 + 新密码以验证身份。修改成功后请用新密码登录。
        </n-text>
        <n-form @keyup.enter="doChangePwd">
          <n-form-item :label="t('auth.register.phone', '手机号', 'Phone')" label-placement="top">
            <n-input v-model:value="cpPhone" :placeholder="t('ui.auth.002', '请输入注册时的手机号', '请输入注册时的手机号')" maxlength="11" />
          </n-form-item>
          <n-form-item :label="t('auth.change.old', '旧密码', 'Current Password')" label-placement="top">
            <n-input v-model:value="cpOldPassword" type="password" show-password-on="click" :placeholder="t('ui.auth.001', '请输入当前密码', '请输入当前密码')" />
          </n-form-item>
          <n-form-item :label="t('auth.change.new', '新密码', 'New Password')" label-placement="top">
            <n-input v-model:value="cpNewPassword" type="password" show-password-on="click" :placeholder="t('auth.register.placeholder.password', '至少 6 位', 'At least 6 chars')" />
          </n-form-item>
          <n-button type="primary" block :loading="loading" @click="doChangePwd">{{ t('auth.change.submit', '确认修改', 'Update Password') }}</n-button>
        </n-form>
        <div class="card-footer">
          <n-button quaternary size="small" @click="mode = 'login'">{{ t('auth.backToLogin', '返回登录', 'Back to login') }}</n-button>
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
  /* 跟随项目主题：--bg-app 由 html.light / dark 切换 */
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
.brand-logo-img {
  height: 88px;
  width: auto;
  margin-bottom: 12px;
  user-select: none;
  -webkit-user-drag: none;
  filter: drop-shadow(0 4px 16px rgba(59, 130, 246, 0.35));
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