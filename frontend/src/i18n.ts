// Minimal i18n: t('key', zh, en) → zh-CN by default, switchable via settings.
// Usage in components:
//   import { t } from '@/i18n'
//   <h1>{t('app.title')}</h1>
//   <h1>{t('app.title', '个人知识小助理', 'Second Brain')}</h1>
//
// Module-level keys live in `translations` below; this is the single source of
// truth for user-facing copy. To translate: add an entry here and use t() in
// the component instead of hardcoding the string.

import { ref } from 'vue'

const STORAGE_KEY = 'hd_locale'
const DEFAULT_LOCALE = 'zh'

export type Locale = 'zh' | 'en'

const locale = ref<Locale>(
  ((typeof localStorage !== 'undefined' && (localStorage.getItem(STORAGE_KEY) as Locale)) ||
    DEFAULT_LOCALE) as Locale,
)

export function setLocale(l: Locale) {
  locale.value = l
  try { localStorage.setItem(STORAGE_KEY, l) } catch {}
  document.documentElement.lang = l === 'zh' ? 'zh-CN' : 'en'
}

export function getLocale(): Locale {
  return locale.value
}

export const t = (key: string, zh: string, en?: string): string => {
  const reg = (translations as Record<string, { zh: string; en: string }>)[key]
  if (reg) return locale.value === 'en' ? reg.en : reg.zh
  return locale.value === 'en' ? en || zh : zh
}

// Translation map. Keys are organised by section so additions are easy to find.
// English translations are concise so the UI never overflows.
export const translations: Record<string, { zh: string; en: string }> = {
  // ===== App =====
  'app.title': { zh: 'smallhouse', en: 'Second Brain' },
  'app.subtitle': { zh: '个人知识小助理', en: 'Personal Knowledge Assistant' },
  'app.brand.tagline': { zh: '多模型 · RAG · 飞书同步', en: 'Multi-LLM · RAG · Feishu Sync' },

  // ===== Navigation =====
  'nav.chat': { zh: '新建对话', en: 'New Chat' },
  'nav.notes': { zh: '知识库', en: 'Knowledge Base' },
  'nav.skills': { zh: '技能 / MCP', en: 'Skills / MCP' },
  'nav.settings': { zh: '设置', en: 'Settings' },
  'nav.logout': { zh: '退出', en: 'Logout' },

  // ===== Auth =====
  'auth.login.title': { zh: '账号登录', en: 'Account Login' },
  'auth.login.account': { zh: '账号', en: 'Account' },
  'auth.login.password': { zh: '密码', en: 'Password' },
  'auth.login.submit': { zh: '登 录', en: 'Log In' },
  'auth.login.placeholder.account': { zh: '请输入手机号', en: 'Enter phone number' },
  'auth.login.placeholder.password': { zh: '请输入密码', en: 'Enter password' },
  'auth.login.forgot': { zh: '忘记密码？', en: 'Forgot password?' },
  'auth.login.toRegister': { zh: '注 册', en: 'Sign Up' },
  'auth.login.success': { zh: '登录成功', en: 'Logged in' },
  'auth.login.fail': { zh: '登录失败', en: 'Login failed' },
  'auth.login.err.account': { zh: '请输入账号（手机号）', en: 'Enter your phone number' },
  'auth.login.err.password': { zh: '请输入密码', en: 'Enter your password' },

  'auth.register.title': { zh: '注册账号', en: 'Create Account' },
  'auth.register.phone': { zh: '手机号', en: 'Phone' },
  'auth.register.password': { zh: '密码', en: 'Password' },
  'auth.register.password2': { zh: '确认密码', en: 'Confirm Password' },
  'auth.register.submit': { zh: '注 册', en: 'Sign Up' },
  'auth.register.placeholder.password': { zh: '至少 6 位', en: 'At least 6 chars' },
  'auth.register.placeholder.password2': { zh: '再次输入密码', en: 'Re-enter password' },
  'auth.register.err.phone': { zh: '请输入正确的手机号', en: 'Enter a valid phone number' },
  'auth.register.err.short': { zh: '密码长度至少 6 位', en: 'Password must be at least 6 chars' },
  'auth.register.err.mismatch': { zh: '两次输入的密码不一致', en: 'Passwords do not match' },
  'auth.register.success': { zh: '注册成功，已自动登录', en: 'Registered and logged in' },
  'auth.register.fail': { zh: '注册失败', en: 'Registration failed' },

  'auth.change.title': { zh: '修改密码', en: 'Change Password' },
  'auth.change.hint': {
    zh: '输入手机号 + 旧密码 + 新密码以验证身份。修改成功后请用新密码登录。',
    en: 'Enter your phone, current password, and a new password. You will be logged out after success.',
  },
  'auth.change.phone': { zh: '手机号', en: 'Phone' },
  'auth.change.old': { zh: '旧密码', en: 'Current Password' },
  'auth.change.new': { zh: '新密码', en: 'New Password' },
  'auth.change.submit': { zh: '确认修改', en: 'Update Password' },
  'auth.change.err.old': { zh: '请输入旧密码以验证身份', en: 'Current password is required' },
  'auth.change.err.short': { zh: '新密码长度至少 6 位', en: 'New password must be at least 6 chars' },
  'auth.change.err.same': { zh: '新密码不能与旧密码相同', en: 'New password cannot match the old one' },
  'auth.change.success': { zh: '密码修改成功，请使用新密码登录', en: 'Password updated, please log in again' },
  'auth.change.fail': { zh: '修改密码失败', en: 'Password change failed' },
  'auth.backToLogin': { zh: '返回登录', en: 'Back to login' },

  // ===== Chat =====
  'chat.welcome': { zh: '嗨，有什么我可以帮助你的？', en: 'Hi! What can I help with?' },
  'chat.input.placeholder': { zh: '输入消息，回车发送，Shift+Enter 换行', en: 'Type a message, Enter to send, Shift+Enter for newline' },
  'chat.input.send': { zh: '发送', en: 'Send' },
  'chat.input.stop': { zh: '停止', en: 'Stop' },
  'chat.kb.label': { zh: '知识库', en: 'Knowledge Base' },
  'chat.kb.on': { zh: '开启', en: 'On' },
  'chat.kb.off': { zh: '关闭', en: 'Off' },
  'chat.kb.hint': { zh: '有问题尽管问，开启后会检索你的知识库回答', en: 'Ask anything - we will search your knowledge base for answers' },
  'chat.perm.label': { zh: '权限', en: 'Permission' },
  'chat.perm.default': { zh: '默认权限', en: 'Default' },
  'chat.perm.full': { zh: '完全访问', en: 'Full Access' },
  'chat.perm.title.default': { zh: '默认权限：Agent 访问本地文件前会先询问你', en: 'Default - Agent prompts before reading local files' },
  'chat.perm.title.full': { zh: '完全访问：Agent 可直接访问本机磁盘，不再询问', en: 'Full Access - Agent can read/write any local file without prompting' },
  'chat.perm.placeholder': { zh: '默认权限', en: 'Default' },
  // HITL 计划审批
  'chat.planApproval.toggle': { zh: '审批', en: 'Approve' },
  'chat.planApproval.tip.on': { zh: '计划审批已开启：研究任务先生成计划，你确认后才执行', en: 'Plan approval ON: research tasks wait for your review before running' },
  'chat.planApproval.tip.off': { zh: '计划审批已关闭：计划自动执行', en: 'Plan approval OFF: plans run automatically' },
  'chat.planApproval.title': { zh: '执行计划待确认', en: 'Plan awaiting review' },
  'chat.planApproval.run': { zh: '运行', en: 'Run' },
  'chat.planApproval.cancel': { zh: '取消', en: 'Cancel' },
  'chat.planApproval.addStep': { zh: '+ 添加步骤', en: '+ Add step' },
  'chat.planApproval.deleteStep': { zh: '删除此步骤', en: 'Delete step' },
  'chat.planApproval.stepPlaceholder': { zh: '检索子问题', en: 'sub-query' },
  'chat.planApproval.cancelled': { zh: '已取消', en: 'Cancelled' },
  'chat.perm.confirm.title': { zh: '⚠️ 确认开启完全访问？', en: '⚠️ Enable Full Access?' },
  'chat.perm.confirm.desc': {
    zh: '开启后，Agent 可以直接读写本机所有磁盘的文件，执行操作前不再询问你。请确认你了解其中的风险。可随时切回「默认权限」恢复逐次确认。',
    en: 'The agent will read/write any local file without prompting. You can switch back to Default anytime.',
  },
  'chat.perm.confirm.cancel': { zh: '取消', en: 'Cancel' },
  'chat.perm.confirm.ok': { zh: '我已了解，开启完全访问', en: 'I understand, enable Full Access' },
  'chat.perm.dialog.title': { zh: '助手请求访问本地资源', en: 'Agent requests local access' },
  'chat.perm.dialog.desc': {
    zh: '助手正在「默认权限」模式下运行，执行以下操作前需要你的确认：',
    en: 'The agent is running in Default mode and needs your confirmation before:',
  },
  'chat.perm.dialog.tool': { zh: '工具', en: 'Tool' },
  'chat.perm.dialog.args': { zh: '参数', en: 'Arguments' },
  'chat.perm.dialog.deny': { zh: '拒绝', en: 'Deny' },
  'chat.perm.dialog.allow': { zh: '允许本次访问', en: 'Allow this time' },
  'chat.perm.dialog.hint': {
    zh: '如不想每次确认，可在输入框下方开启「完全访问」权限',
    en: 'Disable future prompts by switching to Full Access below the input box.',
  },
  'chat.plan.label': { zh: '任务规划', en: 'Planning' },
  'chat.plan.title.on': { zh: '任务规划已开启：复杂问题会先分解为检索计划再执行', en: 'Planning on - complex questions are decomposed before retrieval' },
  'chat.plan.title.off': { zh: '任务规划已关闭：直接检索，不分解子查询', en: 'Planning off - direct retrieval, no sub-queries' },
  'chat.plan.summary': { zh: '检索计划', en: 'Retrieval plan' },
  'chat.plan.replan': { zh: '补检索：', en: 'Re-search: ' },
  'chat.plan.hits': { zh: '（命中 %d 条）', en: '(%d hits)' },
  'chat.tool.status.running': { zh: '运行中…', en: 'running…' },
  'chat.tool.status.ok': { zh: '完成', en: 'done' },
  'chat.tool.status.failed': { zh: '失败', en: 'failed' },
  'chat.report.head': { zh: '周报已生成', en: 'Weekly report ready' },
  'chat.report.saved': { zh: '已存为笔记', en: 'Saved as note' },
  'chat.msg.copy': { zh: '复制', en: 'Copy' },
  'chat.msg.regenerate': { zh: '重新生成', en: 'Regenerate' },
  'chat.msg.delete': { zh: '删除', en: 'Delete' },
  'chat.msg.undo': { zh: '回退', en: 'Undo' },

  // ===== Notes =====
  'notes.title': { zh: '知识库', en: 'Knowledge Base' },
  'notes.empty.title': { zh: '知识库还是空的', en: 'No notes yet' },
  'notes.empty.hint': { zh: '点击下方按钮上传文件、抓取网页或粘贴文本，开始构建你的第二大脑。', en: 'Upload, fetch, or paste to start building your second brain.' },
  'notes.add': { zh: '添加知识', en: 'Add Knowledge' },
  'notes.upload': { zh: '上传文件', en: 'Upload file' },
  'notes.fetch': { zh: '抓取网页', en: 'Fetch URL' },
  'notes.text': { zh: '粘贴文本', en: 'Paste text' },
  'notes.search': { zh: '搜索', en: 'Search' },
  'notes.filter.all': { zh: '全部', en: 'All' },
  'notes.filter.documents': { zh: '文档', en: 'Documents' },
  'notes.filter.images': { zh: '图片', en: 'Images' },
  'notes.filter.web': { zh: '网页', en: 'Web' },
  'notes.filter.text': { zh: '文本', en: 'Text' },
  'notes.open': { zh: '打开', en: 'Open' },
  'notes.delete': { zh: '删除', en: 'Delete' },
  'notes.empty.embedding': { zh: '未入库', en: 'Not indexed' },

  // ===== Skills / MCP =====
  'skills.title': { zh: '技能与 MCP', en: 'Skills & MCP' },
  'skills.tab.skills': { zh: '技能', en: 'Skills' },
  'skills.tab.mcp': { zh: 'MCP', en: 'MCP' },
  'skills.upload': { zh: '上传技能压缩包', en: 'Upload Skill Bundle' },
  'skills.upload.hint': { zh: '将 SKILL.md 打包为 zip 后上传', en: 'Zip a SKILL.md and upload' },
  'skills.upload.err.no_skill_md': { zh: '压缩包中未找到 SKILL.md', en: 'SKILL.md not found in archive' },
  'skills.upload.success': { zh: '技能已安装', en: 'Skill installed' },
  'skills.install': { zh: '安装', en: 'Install' },
  'skills.uninstall': { zh: '卸载', en: 'Uninstall' },

  'mcp.title': { zh: 'MCP 服务', en: 'MCP Servers' },
  'mcp.subtitle': { zh: '把本地命令、HTTP API、知识图谱注册成可调用的工具', en: 'Register local commands, HTTP APIs and knowledge graphs as callable tools' },
  'mcp.tab.presets': { zh: '预设', en: 'Presets' },
  'mcp.tab.servers': { zh: '已配置', en: 'Configured' },
  'mcp.tab.history': { zh: '调用历史', en: 'Call History' },
  'mcp.preset.enable': { zh: '一键启用', en: 'Enable' },
  'mcp.preset.enabled': { zh: '已启用', en: 'Enabled' },
  'mcp.add': { zh: '添加 MCP', en: 'Add MCP' },
  'mcp.add.name': { zh: '名称', en: 'Name' },
  'mcp.add.transport': { zh: '传输方式', en: 'Transport' },
  'mcp.add.command': { zh: '启动命令', en: 'Command' },
  'mcp.add.url': { zh: '服务地址', en: 'URL' },
  'mcp.add.env': { zh: '环境变量', en: 'Environment' },
  'mcp.add.test': { zh: '测试连接', en: 'Test connection' },
  'mcp.add.save': { zh: '保存', en: 'Save' },
  'mcp.history.empty': { zh: '暂无调用记录', en: 'No calls yet' },
  'mcp.history.clear': { zh: '清空记录', en: 'Clear history' },

  // ===== Settings =====
  'settings.title': { zh: '设置', en: 'Settings' },
  'settings.profile': { zh: '个人中心', en: 'Profile' },
  'settings.models': { zh: '自定义模型', en: 'Custom Models' },
  'settings.knowledge': { zh: '知识库配置', en: 'Knowledge Base' },
  'settings.appearance': { zh: '外观与语言', en: 'Appearance & Language' },
  'settings.theme.dark': { zh: '深色', en: 'Dark' },
  'settings.theme.light': { zh: '浅色', en: 'Light' },
  'settings.lang.zh': { zh: '中文', en: 'Chinese' },
  'settings.lang.en': { zh: '英文', en: 'English' },
  'settings.account.export': { zh: '导出我的数据', en: 'Export my data' },
  'settings.account.delete': { zh: '注销账号', en: 'Delete account' },

  // ===== Common =====
  'common.cancel': { zh: '取消', en: 'Cancel' },
  'common.confirm': { zh: '确定', en: 'Confirm' },
  'common.delete': { zh: '删除', en: 'Delete' },
  'common.save': { zh: '保存', en: 'Save' },
  'common.loading': { zh: '加载中…', en: 'Loading…' },
  'common.empty': { zh: '暂无数据', en: 'No data' },
  'common.retry': { zh: '重试', en: 'Retry' },
  'common.yes': { zh: '是', en: 'Yes' },
  'common.no': { zh: '否', en: 'No' },
  'common.error.unknown': { zh: '未知错误', en: 'Unknown error' },

  // ===== Command Palette =====
  'palette.title': { zh: '搜索命令、会话或操作…', en: 'Search commands, sessions, or actions…' },
  'palette.empty': { zh: '没有匹配的命令', en: 'No matching commands' },
  'palette.footer.updown': { zh: '选择', en: 'Select' },
  'palette.footer.enter': { zh: '执行', en: 'Run' },
  'palette.footer.esc': { zh: '关闭', en: 'Close' },
  'palette.group.nav': { zh: '导航', en: 'Navigation' },
  'palette.group.theme': { zh: '外观', en: 'Appearance' },
  'palette.group.rag': { zh: '对话', en: 'Chat' },
  'palette.group.models': { zh: '模型', en: 'Models' },
  'palette.group.sessions': { zh: '会话', en: 'Sessions' },
  'palette.group.recent': { zh: '最近会话', en: 'Recent' },
}

export default { t, setLocale, getLocale, translations }