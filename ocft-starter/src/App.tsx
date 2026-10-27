import { MotionConfig } from 'motion/react'
import { MessageSquareIcon, PanelLeftOpenIcon, PanelRightOpenIcon } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

import { cn } from '@/lib/utils'

import { AdminPage } from '@/components/admin/admin-page'
import { AppHeader } from '@/components/app-header'
import { BootSplash } from '@/components/auth/boot-splash'
import { LoginPage } from '@/components/auth/login-page'
import { DataCatalog } from '@/components/catalog/data-catalog'
import { DataListPage } from '@/components/catalog/data-list-page'
import { ChatPanel } from '@/components/chat/chat-panel'
import { DimensionPage } from '@/components/report/dimension-page'
import { RunInspector } from '@/components/run/run-inspector'
import { SkillCenterPage } from '@/components/skills/skill-center-page'
import { LoanPage } from '@/components/workspace/loan-page'
import { SCENARIO_ID, applicationQuestion, getScenario } from '@/data/scenario'
import { useAgentSession } from '@/hooks/use-agent-session'
import { navIdFromRoute, useAppRoute, useDocumentTitle } from '@/hooks/use-app-route'
import { useAuth } from '@/hooks/use-auth'
import { useHealth } from '@/hooks/use-backend'
import { homePath, loginPath, navigate, tablesPath, workspacePath, workspaceReportHref } from '@/lib/app-route'
import { DEFAULT_ENTERPRISE_QUESTION, applyEnterpriseToQuestion } from '@/lib/enterprise-input'
import { visibleListTables, visibleLoanSections } from '@/lib/permissions'

export default function App() {
  const auth = useAuth()
  const actorId = auth.user?.username ?? ''
  const { route, search } = useAppRoute()
  // 尽调报告页的贷款编号过滤：智能尽调「查看报告」跳转时带入
  const reportApplicationId = route.page === 'workspace' && route.section === 'reports'
    ? (new URLSearchParams(search).get('applicationId') ?? '').trim()
    : ''
  const scenario = getScenario(SCENARIO_ID)
  useDocumentTitle(route, scenario.title)
  const health = useHealth()
  const session = useAgentSession(actorId || 'anonymous', scenario.id)
  const [picked, setPicked] = useState<{ id: string; latestId: string | null } | null>(null)
  const [processId, setProcessId] = useState<string | null>(null)
  const [inspectorFlash, setInspectorFlash] = useState(false)
  const [catalogOpen, setCatalogOpen] = useState(true)
  const [chatOpen, setChatOpen] = useState(true)
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const [selectedEnterpriseId, setSelectedEnterpriseId] = useState<string | null>(null)
  const [selectedApplicationId, setSelectedApplicationId] = useState<string | null>(null)
  const [chatInput, setChatInput] = useState('')
  const fillQuestionRef = useRef<(question: string) => void>(() => {})
  const onBindFillQuestion = useCallback((fill: (question: string) => void) => {
    fillQuestionRef.current = fill
  }, [])
  const emptyEnterpriseExample = DEFAULT_ENTERPRISE_QUESTION
  const latest = session.turns.at(-1) ?? null
  const latestId = latest?.id ?? null
  const selected = (picked && picked.latestId === latestId
    ? session.turns.find((t) => t.id === picked.id)
    : null) ?? latest
  const activeNav = navIdFromRoute(route)

  const listTables = useMemo(() => visibleListTables(auth.user), [auth.user])
  const loanSections = useMemo(() => visibleLoanSections(auth.user), [auth.user])

  useEffect(() => {
    if (auth.booting) return
    if (!auth.user && route.page !== 'login') {
      navigate(loginPath(), true)
      return
    }
    if (auth.user && route.page === 'login') {
      navigate(homePath(), true)
      return
    }
    if (auth.user && route.page === 'admin' && !auth.isAdmin) {
      navigate(homePath(), true)
      return
    }
    if (auth.user && route.page === 'report' && !auth.canDdSteps) {
      navigate(homePath(), true)
      return
    }
    if (auth.user && route.page === 'workspace') {
      if (loanSections.length === 0) {
        navigate(homePath(), true)
        return
      }
      if (!loanSections.includes(route.section)) {
        navigate(workspacePath(loanSections[0]), true)
        return
      }
    }
    if (auth.user && route.page === 'tables') {
      // 只读无「数据列表」菜单；直链也回智能尽调
      if (!auth.canCatalog || !auth.canApplications || listTables.length === 0) {
        navigate(homePath(), true)
        return
      }
      // 贷款申请已移到「贷款管理」，旧链接转过去
      if (route.table.kind === 'applications' && loanSections.includes('applications')) {
        navigate(workspacePath('applications'), true)
        return
      }
      if (!listTables.some((t) => t.table === route.table.table)) {
        navigate(tablesPath(listTables[0].table), true)
      }
    }
  }, [auth.booting, auth.user, auth.isAdmin, auth.canDdSteps, auth.canConfirm, auth.canCatalog, auth.canApplications, listTables, loanSections, route])

  if (auth.booting) {
    return <BootSplash />
  }

  if (!auth.user || route.page === 'login') {
    return (
      <MotionConfig reducedMotion="user">
        <LoginPage
          onLogin={async (username, password) => {
            await auth.login(username, password)
            navigate(homePath())
          }}
        />
      </MotionConfig>
    )
  }

  return (
    <MotionConfig reducedMotion="user">
      <div className="app-shell flex h-full flex-col overflow-hidden">
        <AppHeader
          health={health}
          user={auth.user}
          canWorkbench={auth.canWorkbench}
          canCatalog={auth.canCatalog}
          canApplications={auth.canApplications}
          canDdSteps={auth.canDdSteps}
          canConfirm={auth.canConfirm}
          isAdmin={auth.isAdmin}
          title={scenario.title}
          activeNav={activeNav}
          onNavigate={navigate}
          workspaceHref={workspacePath(loanSections[0] ?? 'applications')}
          onLogout={() => {
            void auth.logout().then(() => {
              session.reset()
              navigate(loginPath())
            })
          }}
        />
        <main className="main-scroll flex min-h-0 w-full flex-1 flex-col overflow-y-auto px-4 py-4 lg:px-6 xl:px-8">
          {route.page === 'admin' ? (
            <AdminPage />
          ) : route.page === 'tables' ? (
            <DataListPage
              actorId={actorId}
              table={route.table}
              tables={listTables}
              allowWrite={auth.canCatalogWrite}
              onNavigate={navigate}
            />
          ) : route.page === 'report' ? (
            <DimensionPage
              key={route.dim.slug}
              actorId={actorId}
              dim={route.dim}
              onNavigate={navigate}
            />
          ) : route.page === 'workspace' ? (
            <LoanPage
              actorId={actorId}
              section={route.section}
              sections={loanSections}
              allowWrite={auth.canCatalogWrite}
              allowReview={auth.canConfirm}
              applicationId={reportApplicationId}
              onNavigate={navigate}
            />
          ) : route.page === 'skills' ? (
            <SkillCenterPage />
          ) : (
            <div className={cn(
              'grid grid-cols-1 gap-4 lg:min-h-0 lg:flex-1',
              workbenchCols(catalogOpen, chatOpen, inspectorOpen),
            )}>
              {catalogOpen ? (
                <div className="min-h-[320px] lg:h-full lg:min-h-0">
                  <DataCatalog
                    key={`${actorId}:${scenario.id}`}
                    actorId={actorId}
                    scenarioId={scenario.id}
                    chatInput={chatInput}
                    emptyEnterpriseExample={emptyEnterpriseExample}
                    selectedEnterpriseId={selectedEnterpriseId}
                    selectedApplicationId={selectedApplicationId}
                    showApplications={auth.canApplications}
                    onViewReport={auth.canConfirm
                      ? (applicationId) => navigate(workspaceReportHref(applicationId))
                      : undefined}
                    onSelectEnterprise={(enterpriseId) => {
                      const next = applyEnterpriseToQuestion(chatInput, enterpriseId, emptyEnterpriseExample)
                      setSelectedEnterpriseId(enterpriseId)
                      setSelectedApplicationId(null)
                      fillQuestionRef.current(next)
                      setChatOpen(true)
                    }}
                    onSelectApplication={(applicationId) => {
                      setSelectedApplicationId(applicationId)
                      setSelectedEnterpriseId(null)
                      fillQuestionRef.current(applicationQuestion(applicationId))
                      setChatOpen(true)
                    }}
                    onCollapse={() => setCatalogOpen(false)}
                  />
                </div>
              ) : (
                <SideRail label="业务数据" icon={<PanelLeftOpenIcon />} onExpand={() => setCatalogOpen(true)} />
              )}
              {chatOpen ? (
                <div className="min-h-[320px] min-w-0 rounded-xl lg:h-full lg:min-h-0">
                  <ChatPanel
                    scenario={scenario}
                    actorId={actorId}
                    turns={session.turns}
                    busy={session.busy}
                    conversationId={session.conversationId}
                    selectedId={selected?.id ?? null}
                    processId={processId}
                    onBindFillQuestion={onBindFillQuestion}
                    onInputChange={setChatInput}
                    onCollapse={() => setChatOpen(false)}
                    onSelect={(id) => {
                      if (inspectorOpen && processId === id) {
                        setInspectorOpen(false)
                        setProcessId(null)
                        return
                      }
                      setPicked({ id, latestId })
                      setProcessId(id)
                      setInspectorOpen(true)
                      setInspectorFlash(true)
                      window.setTimeout(() => setInspectorFlash(false), 1200)
                      window.setTimeout(() => {
                        document.getElementById('run-inspector')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
                      }, 50)
                    }}
                    onAsk={(q, images) => void session.ask(q, images)}
                    onReset={() => {
                      session.reset()
                      setPicked(null)
                      setProcessId(null)
                    }}
                    onOpenConversation={async (item) => {
                      setPicked(null)
                      setProcessId(null)
                      return session.open(item.conversationId)
                    }}
                  />
                </div>
              ) : (
                <SideRail label="企业信贷智能体" icon={<MessageSquareIcon />} onExpand={() => setChatOpen(true)} />
              )}
              {inspectorOpen ? (
                <div className={cn(
                  'min-h-[320px] rounded-xl transition-shadow lg:h-full lg:min-h-0 lg:overflow-y-auto',
                  inspectorFlash && 'ring-2 ring-brand',
                )}>
                  <RunInspector
                    turn={selected}
                    onCollapse={() => {
                      setInspectorOpen(false)
                      setProcessId(null)
                    }}
                  />
                </div>
              ) : (
                <SideRail label="执行过程" icon={<PanelRightOpenIcon />} onExpand={() => setInspectorOpen(true)} />
              )}
            </div>
          )}
        </main>
        <footer className="app-footer shrink-0 py-4 text-center font-mono text-[11px] tracking-wide">
          © 2026 金融壹账通 · 比赛演示作品 · 运行时模型 deepseek-v4.1-flash · 所有结论来自后端实时取证
        </footer>
      </div>
    </MotionConfig>
  )
}

function workbenchCols(catalogOpen: boolean, chatOpen: boolean, inspectorOpen: boolean): string {
  const key = `${catalogOpen ? 1 : 0}${chatOpen ? 1 : 0}${inspectorOpen ? 1 : 0}`
  // 业务数据栏大屏封顶 30rem+100px；对话与执行过程都收起时不再限制，让业务数据撑满
  const map: Record<string, string> = {
    '111': 'lg:grid-cols-[minmax(0,calc(30rem+100px))_minmax(0,1fr)_minmax(0,24rem)]',
    '110': 'lg:grid-cols-[minmax(0,calc(30rem+100px))_minmax(0,1fr)_2.5rem]',
    '101': 'lg:grid-cols-[minmax(0,calc(30rem+100px))_2.5rem_minmax(0,1fr)]',
    '100': 'lg:grid-cols-[minmax(0,1fr)_2.5rem_2.5rem]',
    '011': 'lg:grid-cols-[2.5rem_minmax(0,1fr)_minmax(0,24rem)]',
    '010': 'lg:grid-cols-[2.5rem_minmax(0,1fr)_2.5rem]',
    '001': 'lg:grid-cols-[2.5rem_2.5rem_minmax(0,1fr)]',
    '000': 'lg:grid-cols-[2.5rem_2.5rem_2.5rem]',
  }
  return map[key]
}

function SideRail({ label, icon, onExpand }: {
  label: string
  icon: ReactNode
  onExpand: () => void
}) {
  return (
    <button
      type="button"
      aria-expanded={false}
      onClick={onExpand}
      className="surface-panel flex h-10 w-full shrink-0 items-center justify-center gap-2 rounded-xl text-sm text-muted-foreground transition-colors hover:text-brand lg:h-full lg:w-auto lg:flex-col"
    >
      {icon}
      <span className="lg:[writing-mode:vertical-rl]">{label}</span>
    </button>
  )
}
