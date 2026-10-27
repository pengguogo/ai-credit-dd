import { BootSplash } from '@/components/auth/boot-splash'
import { LoginPage } from '@/components/auth/login-page'
import { ReportPreviewPage } from '@/components/report/preview/report-preview-page'
import { useAuth } from '@/hooks/use-auth'

/** 预览页入口：校验 runId 与登录态，再按 runId 读取报告快照。 */
export function PreviewApp() {
  const auth = useAuth()
  const runId = new URLSearchParams(window.location.search).get('runId')
  if (!runId) return <div className="p-10"><h1 className="text-xl font-semibold">缺少报告编号</h1><p className="mt-3">请在「智能尽调」生成结果下方点击“预览报告”。</p><a className="mt-4 inline-block underline" href="/">返回智能尽调</a></div>
  if (auth.booting) return <div className="h-dvh"><BootSplash /></div>
  if (!auth.user) return <LoginPage onLogin={async (username, password) => { await auth.login(username, password) }} />
  return <ReportPreviewPage actorId={auth.user.username} runId={runId} />
}
