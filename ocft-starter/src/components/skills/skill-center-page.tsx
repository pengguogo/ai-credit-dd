import {
  ArrowDownIcon,
  BotIcon,
  Building2Icon,
  CheckCircle2Icon,
  FileCheck2Icon,
  FileTextIcon,
  GaugeIcon,
  GitBranchIcon,
  RadarIcon,
  SearchIcon,
  ShieldAlertIcon,
  ShieldCheckIcon,
  SparklesIcon,
  WorkflowIcon,
} from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  AGENT_SKILLS,
  SKILL_CATEGORY_LABEL,
  SKILL_TOOL_COUNT,
  type AgentSkill,
  type SkillCategory,
} from '@/data/skill-catalog'
import { toolLabel } from '@/lib/format'
import { cn } from '@/lib/utils'

type SkillFilter = 'all' | SkillCategory

const FILTERS: { id: SkillFilter; label: string }[] = [
  { id: 'all', label: '全部能力' },
  { id: 'orchestration', label: '智能编排' },
  { id: 'insight', label: '取证洞察' },
  { id: 'risk', label: '风险识别' },
  { id: 'decision', label: '决策测算' },
  { id: 'delivery', label: '成果交付' },
]

const CATEGORY_CLASS: Record<SkillCategory, string> = {
  orchestration: 'border-brand/35 bg-brand-soft text-brand',
  insight: 'border-tech/35 bg-tech-soft text-tech',
  risk: 'border-rose-400/30 bg-rose-500/10 text-rose-600',
  decision: 'border-amber-400/35 bg-amber-500/10 text-amber-700',
  delivery: 'border-orange-400/35 bg-orange-500/10 text-orange-700',
}

function AgentIcon({ role, className }: { role: string; className?: string }) {
  const props = { className: cn('size-5', className), 'aria-hidden': true as const }
  if (role === 'controller') return <WorkflowIcon {...props} />
  if (role === 'business') return <Building2Icon {...props} />
  if (role === 'finance') return <GaugeIcon {...props} />
  if (role === 'opinion') return <RadarIcon {...props} />
  if (role === 'fraud') return <ShieldAlertIcon {...props} />
  if (role === 'rating') return <FileCheck2Icon {...props} />
  return <FileTextIcon {...props} />
}

function Stat({ value, label, detail, icon }: {
  value: string
  label: string
  detail: string
  icon: ReactNode
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-slate-950/35 px-4 py-3 backdrop-blur-sm">
      <div className="flex items-center justify-between gap-2">
        <span className="text-2xl font-semibold tracking-tight text-white">{value}</span>
        <span className="text-brand [&>svg]:size-5">{icon}</span>
      </div>
      <p className="mt-1 text-xs font-medium text-slate-200">{label}</p>
      <p className="mt-0.5 text-[11px] text-slate-400">{detail}</p>
    </div>
  )
}

function FlowNode({ role, name, skill, className }: {
  role: string
  name: string
  skill: string
  className?: string
}) {
  return (
    <div className={cn('rounded-xl border border-border/70 bg-card/80 px-3 py-3 shadow-sm', className)}>
      <div className="flex items-center gap-2">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-tech-soft text-tech">
          <AgentIcon role={role} className="size-4" />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{name} Agent</p>
          <p className="truncate font-mono text-[10px] text-muted-foreground">{skill}</p>
        </div>
      </div>
    </div>
  )
}

function ArchitectureMap() {
  const byRole = Object.fromEntries(AGENT_SKILLS.map((skill) => [skill.role, skill]))
  const parallel = ['business', 'finance', 'opinion'].map((role) => byRole[role])
  const downstream = ['fraud', 'rating', 'report'].map((role) => byRole[role])
  const controller = byRole.controller
  return (
    <section className="surface-panel overflow-hidden rounded-2xl" aria-labelledby="skill-map-title">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border/70 px-5 py-4">
        <div>
          <p className="font-mono text-[10px] font-medium tracking-[0.14em] text-brand uppercase">Agent orchestration graph</p>
          <h2 id="skill-map-title" className="mt-1 text-lg font-semibold tracking-tight">主控与专业 Agent 编排图</h2>
          <p className="mt-1 text-xs text-muted-foreground">先并行取证，再按依赖完成风险识别、评级授信和报告交付。</p>
        </div>
        <Badge variant="outline" className="border-success/30 bg-success/5 text-success">
          <CheckCircle2Icon />运行时已绑定
        </Badge>
      </div>
      <div className="bg-tech-soft/20 px-5 py-5">
        <div className="mx-auto max-w-4xl">
          <FlowNode
            role={controller.role}
            name={controller.agentName}
            skill={controller.skillName}
            className="mx-auto max-w-sm border-brand/35 bg-brand-soft/30"
          />
          <div className="flex h-8 items-center justify-center text-muted-foreground"><ArrowDownIcon className="size-4" /></div>
          <p className="mb-2 text-center font-mono text-[10px] tracking-[0.12em] text-muted-foreground uppercase">Parallel evidence acquisition</p>
          <div className="grid gap-2 sm:grid-cols-3">
            {parallel.map((skill) => (
              <FlowNode key={skill.role} role={skill.role} name={skill.agentName} skill={`${skill.skillName}@${skill.version}`} />
            ))}
          </div>
          <div className="flex h-8 items-center justify-center text-muted-foreground"><ArrowDownIcon className="size-4" /></div>
          <div className="mx-auto grid max-w-2xl gap-2 sm:grid-cols-[1fr_auto_1fr_auto_1fr] sm:items-center">
            {downstream.map((skill, index) => (
              <div key={skill.role} className="contents">
                {index > 0 && <span className="hidden text-center text-muted-foreground sm:block">→</span>}
                <FlowNode role={skill.role} name={skill.agentName} skill={`${skill.skillName}@${skill.version}`} />
              </div>
            ))}
          </div>
          <div className="mt-3 flex items-center justify-center gap-2 rounded-lg border border-dashed border-success/35 bg-success/5 px-3 py-2 text-xs text-success">
            <ShieldCheckIcon className="size-4" aria-hidden />发布前事实校验 · 数字、评级、额度与规则编号逐项核对
          </div>
        </div>
      </div>
    </section>
  )
}

function SkillCard({ skill }: { skill: AgentSkill }) {
  const isController = skill.role === 'controller'
  return (
    <Card className={cn('h-full transition-transform duration-200 hover:-translate-y-0.5 hover:shadow-md', isController && 'lg:col-span-2')}>
      <CardHeader className="border-b border-border/60 pb-4">
        <div className="flex items-start gap-3">
          <span className={cn('flex size-10 shrink-0 items-center justify-center rounded-xl border', CATEGORY_CLASS[skill.category])}>
            <AgentIcon role={skill.role} />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-semibold tracking-tight">{skill.agentName} Agent</h3>
              <Badge variant="outline" className={CATEGORY_CLASS[skill.category]}>{SKILL_CATEGORY_LABEL[skill.category]}</Badge>
              <span className="ml-auto inline-flex items-center gap-1 text-[11px] text-success">
                <span className="size-1.5 rounded-full bg-success" aria-hidden />已装载
              </span>
            </div>
            <p className="mt-1 font-mono text-xs text-brand">{skill.skillName}@{skill.version}</p>
            <p className="mt-2 text-sm leading-relaxed text-foreground/80">{skill.summary}</p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="grid gap-4 pt-0 sm:grid-cols-2">
        <div>
          <p className="text-xs font-medium">核心能力</p>
          <ul className="mt-2 space-y-1.5 text-xs text-muted-foreground">
            {skill.capabilities.map((item) => (
              <li key={item} className="flex gap-2"><CheckCircle2Icon className="mt-0.5 size-3.5 shrink-0 text-tech" />{item}</li>
            ))}
          </ul>
        </div>
        <div>
          <p className="text-xs font-medium">治理边界</p>
          <ul className="mt-2 space-y-1.5 text-xs text-muted-foreground">
            {skill.safeguards.map((item) => (
              <li key={item} className="flex gap-2"><ShieldCheckIcon className="mt-0.5 size-3.5 shrink-0 text-success" />{item}</li>
            ))}
          </ul>
        </div>
        <div className="rounded-lg border border-border/60 bg-muted/25 p-3">
          <p className="font-mono text-[10px] tracking-wide text-muted-foreground uppercase">Input contract</p>
          <p className="mt-1 text-xs leading-relaxed">{skill.inputs}</p>
        </div>
        <div className="rounded-lg border border-border/60 bg-muted/25 p-3">
          <p className="font-mono text-[10px] tracking-wide text-muted-foreground uppercase">Output asset</p>
          <p className="mt-1 text-xs leading-relaxed">{skill.outputs}</p>
        </div>
        <div className="sm:col-span-2">
          <p className="text-[11px] text-muted-foreground">工具绑定</p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {skill.tools.map((tool) => (
              <span key={tool} title={tool} className="rounded-md border border-tech/25 bg-tech-soft/50 px-2 py-1 text-[11px] text-tech">
                {toolLabel(tool)}
              </span>
            ))}
          </div>
        </div>
        <dl className="grid gap-x-4 gap-y-2 border-t border-border/60 pt-3 text-[11px] text-muted-foreground sm:col-span-2 sm:grid-cols-2">
          <div><dt className="inline font-medium text-foreground">执行阶段：</dt><dd className="inline">{skill.stage}</dd></div>
          <div><dt className="inline font-medium text-foreground">依赖：</dt><dd className="inline">{skill.dependencies.join(' → ') || '无上游依赖'}</dd></div>
          <div><dt className="inline font-medium text-foreground">配置来源：</dt><dd className="inline font-mono">{skill.source}</dd></div>
          <div><dt className="inline font-medium text-foreground">运行时绑定：</dt><dd className="inline">{skill.runtimeBinding}</dd></div>
        </dl>
      </CardContent>
    </Card>
  )
}

export function SkillCenterPage() {
  const [filter, setFilter] = useState<SkillFilter>('all')
  const [query, setQuery] = useState('')
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    return AGENT_SKILLS.filter((skill) => {
      if (filter !== 'all' && skill.category !== filter) return false
      if (!q) return true
      return [
        skill.agentName,
        skill.skillName,
        skill.skillTitle,
        skill.summary,
        skill.duty,
        ...skill.capabilities,
        ...skill.tools,
      ].some((value) => value.toLowerCase().includes(q))
    })
  }, [filter, query])

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 pb-6">
      <header className="relative overflow-hidden rounded-2xl border border-slate-700/70 bg-slate-950 px-5 py-6 text-slate-100 shadow-xl sm:px-7">
        <div aria-hidden className="absolute inset-0 bg-[radial-gradient(circle_at_82%_10%,rgba(249,115,22,0.2),transparent_30%),radial-gradient(circle_at_15%_90%,rgba(14,165,233,0.18),transparent_36%)]" />
        <div aria-hidden className="absolute inset-0 opacity-20 [background-image:linear-gradient(rgba(148,163,184,.12)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,.12)_1px,transparent_1px)] [background-size:28px_28px]" />
        <div className="relative">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="max-w-3xl">
              <div className="flex items-center gap-2 font-mono text-[11px] font-medium tracking-[0.16em] text-brand uppercase">
                <SparklesIcon className="size-4" aria-hidden />Agent capability registry
              </div>
              <h1 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">Agent Skill 技能中心</h1>
              <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-300">
                将主控编排与六个专业 Agent 的业务 Skill、工具、输入输出契约和治理边界集中呈现，能力可发现、可复用、可追溯。
              </p>
            </div>
            <Badge variant="outline" className="border-brand/40 bg-brand/10 text-brand">
              <GitBranchIcon />主控 + 六角色
            </Badge>
          </div>
          <div className="mt-6 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <Stat value="7" label="Agent 节点" detail="1 个主控 + 6 个专业角色" icon={<BotIcon />} />
            <Stat value="6" label="版本化 Skill" detail="运行时注入专业角色消息" icon={<SparklesIcon />} />
            <Stat value={String(SKILL_TOOL_COUNT)} label="业务工具绑定" detail="确定性计算与取证能力" icon={<WorkflowIcon />} />
            <Stat value="100%" label="发布前校验" detail="证据、数字与结论可追溯" icon={<ShieldCheckIcon />} />
          </div>
        </div>
      </header>

      <ArchitectureMap />

      <section aria-labelledby="skill-catalog-title">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="font-mono text-[10px] font-medium tracking-[0.14em] text-brand uppercase">Skill catalog</p>
            <h2 id="skill-catalog-title" className="mt-1 text-lg font-semibold tracking-tight">业务技能目录</h2>
            <p className="mt-1 text-xs text-muted-foreground">人员登录角色与 Agent 角色相互独立；这里展示的是系统实际执行的 Agent 能力。</p>
          </div>
          <label className="relative w-full sm:w-72">
            <span className="sr-only">搜索技能</span>
            <SearchIcon className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索 Agent、Skill 或工具" className="pl-9" />
          </label>
        </div>
        <div className="mt-3 flex flex-wrap gap-1.5" role="group" aria-label="技能分类">
          {FILTERS.map((item) => (
            <Button
              key={item.id}
              type="button"
              size="sm"
              variant={filter === item.id ? 'default' : 'outline'}
              className="cursor-pointer"
              onClick={() => setFilter(item.id)}
            >
              {item.label}
            </Button>
          ))}
        </div>
        {visible.length > 0 ? (
          <div className="mt-3 grid gap-3 lg:grid-cols-2">
            {visible.map((skill) => <SkillCard key={skill.role} skill={skill} />)}
          </div>
        ) : (
          <div className="surface-panel mt-3 rounded-xl px-5 py-10 text-center">
            <SearchIcon className="mx-auto size-6 text-muted-foreground" />
            <p className="mt-2 text-sm font-medium">没有匹配的技能</p>
            <p className="mt-1 text-xs text-muted-foreground">请调整搜索词或切换技能分类。</p>
          </div>
        )}
      </section>

      <section className="grid gap-3 sm:grid-cols-3" aria-label="Skill 技术特性">
        {[
          ['版本可追溯', '每次角色运行记录 name@version，可在 contextSnapshot.skillsApplied 核对。'],
          ['契约可校验', '缺字段、角色重复认领或未知绑定会抛出 SkillError，拒绝带病启动。'],
          ['模型有边界', '数字由确定性工具计算，Skill 约束模型只做解读、成文与边界披露。'],
        ].map(([title, detail], index) => (
          <div key={title} className="surface-panel rounded-xl p-4">
            <p className="flex items-center gap-2 text-sm font-medium">
              {index === 0 ? <GitBranchIcon className="size-4 text-brand" /> : index === 1 ? <ShieldCheckIcon className="size-4 text-tech" /> : <BotIcon className="size-4 text-success" />}
              {title}
            </p>
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{detail}</p>
          </div>
        ))}
      </section>
    </div>
  )
}
