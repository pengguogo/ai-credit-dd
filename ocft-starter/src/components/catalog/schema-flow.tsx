/**
 * 尽调维度只读关系图：节点 + SVG 连线，数据来自目录接口；界面只展示维度中文名，不展示表名与键名。
 */
import { useMemo, useState } from 'react'

import { LIST_TABLES } from '@/lib/catalog-tables'
import { cn } from '@/lib/utils'

type RelRow = {
  mainTable?: string | number | null
  childTable?: string | number | null
  primaryKey?: string | number | null
  foreignKey?: string | number | null
  note?: string | number | null
}

type Edge = {
  id: string
  from: string
  to: string
  primaryKey: string
  foreignKey: string
  note: string
}

type Point = { x: number; y: number }

const NODE_W = 168
const NODE_H = 56
const VIEW_W = 920
const VIEW_H = 560

function text(value: string | number | null | undefined): string {
  return value == null || value === '' ? '' : String(value)
}

function displayName(table: string): string {
  return LIST_TABLES.find((item) => item.table === table)?.label ?? table
}

function buildEdges(rows: RelRow[]): Edge[] {
  return rows
    .map((row, index) => {
      const from = text(row.mainTable)
      const to = text(row.childTable)
      if (!from || !to) return null
      return {
        id: `${from}->${to}:${index}`,
        from,
        to,
        primaryKey: text(row.primaryKey) || '—',
        foreignKey: text(row.foreignKey) || '—',
        note: text(row.note),
      }
    })
    .filter((e): e is Edge => e != null)
}

/** 以出度最高的表为中心，其余按扇形排布；另有边的表尽量靠近两侧。 */
function layoutNodes(edges: Edge[]): Map<string, Point> {
  const names = Array.from(new Set(edges.flatMap((e) => [e.from, e.to])))
  const outDegree = new Map<string, number>()
  for (const name of names) outDegree.set(name, 0)
  for (const e of edges) outDegree.set(e.from, (outDegree.get(e.from) ?? 0) + 1)

  const hub = [...outDegree.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? names[0]
  const satellites = names.filter((n) => n !== hub)
  const pos = new Map<string, Point>()
  const cx = VIEW_W / 2
  const cy = VIEW_H / 2
  pos.set(hub, { x: cx, y: cy })

  const radius = Math.min(VIEW_W, VIEW_H) * 0.36
  satellites.forEach((name, i) => {
    // 从上方偏左起顺时针，避免与标题重叠
    const angle = -Math.PI / 2 + (i / Math.max(satellites.length, 1)) * Math.PI * 2
      + Math.PI / satellites.length
    pos.set(name, {
      x: cx + Math.cos(angle) * radius,
      y: cy + Math.sin(angle) * radius * 0.92,
    })
  })
  return pos
}

function edgePath(from: Point, to: Point): string {
  const dx = to.x - from.x
  const dy = to.y - from.y
  const dist = Math.hypot(dx, dy) || 1
  // 从节点边缘出发，避免线穿进卡片
  const ux = dx / dist
  const uy = dy / dist
  const startPad = NODE_W * 0.42
  const endPad = NODE_W * 0.42
  const x1 = from.x + ux * startPad
  const y1 = from.y + uy * startPad
  const x2 = to.x - ux * endPad
  const y2 = to.y - uy * endPad
  const mx = (x1 + x2) / 2
  const my = (y1 + y2) / 2
  // 轻微外凸，放射线更清晰
  const nx = -uy * dist * 0.08
  const ny = ux * dist * 0.08
  return `M ${x1} ${y1} Q ${mx + nx} ${my + ny} ${x2} ${y2}`
}


export function SchemaFlow({ rows }: { rows: RelRow[] }) {
  const edges = useMemo(() => buildEdges(rows), [rows])
  const positions = useMemo(() => layoutNodes(edges), [edges])
  const nodes = useMemo(() => Array.from(positions.keys()), [positions])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [hoverId, setHoverId] = useState<string | null>(null)
  const [focusNode, setFocusNode] = useState<string | null>(null)

  const highlightId = hoverId ?? selectedId
  const activeEdge = edges.find((e) => e.id === (selectedId ?? hoverId)) ?? null

  if (edges.length === 0) {
    return <p className="px-1 py-6 text-sm text-muted-foreground">没有尽调维度数据</p>
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="catalog-scroll relative min-h-0 flex-1 rounded-xl border border-border/80 bg-card/40">
        <svg
          viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
          className="h-full min-h-[28rem] w-full"
          role="img"
          aria-label="尽调维度关系图"
          onMouseLeave={() => {
            setFocusNode(null)
            setHoverId(null)
          }}
        >
          <defs>
            <marker
              id="schema-arrow"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" className="fill-tech" />
            </marker>
            <marker
              id="schema-arrow-active"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="8"
              markerHeight="8"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" className="fill-brand" />
            </marker>
            <radialGradient id="schema-hub-glow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="rgb(233 85 4 / 0.2)" />
              <stop offset="100%" stopColor="rgb(233 85 4 / 0)" />
            </radialGradient>
          </defs>

          {/* 背景网格 */}
          <g aria-hidden opacity="0.35">
            {Array.from({ length: 20 }, (_, i) => (
              <line
                key={`v${i}`}
                x1={(i + 1) * (VIEW_W / 20)}
                y1={0}
                x2={(i + 1) * (VIEW_W / 20)}
                y2={VIEW_H}
                stroke="currentColor"
                className="text-border"
                strokeWidth="0.5"
              />
            ))}
            {Array.from({ length: 12 }, (_, i) => (
              <line
                key={`h${i}`}
                x1={0}
                y1={(i + 1) * (VIEW_H / 12)}
                x2={VIEW_W}
                y2={(i + 1) * (VIEW_H / 12)}
                stroke="currentColor"
                className="text-border"
                strokeWidth="0.5"
              />
            ))}
          </g>

          {(() => {
            const hub = [...edges.reduce((m, e) => {
              m.set(e.from, (m.get(e.from) ?? 0) + 1)
              return m
            }, new Map<string, number>())].sort((a, b) => b[1] - a[1])[0]?.[0]
            const hubPos = hub ? positions.get(hub) : null
            return hubPos ? (
              <circle cx={hubPos.x} cy={hubPos.y} r={90} fill="url(#schema-hub-glow)" />
            ) : null
          })()}

          {/* 连线 */}
          {edges.map((edge) => {
            const from = positions.get(edge.from)
            const to = positions.get(edge.to)
            if (!from || !to) return null
            const active = highlightId === edge.id
              || (focusNode != null && (focusNode === edge.from || focusNode === edge.to))
            const dimmed = (highlightId != null || focusNode != null) && !active
            return (
              <g
                key={edge.id}
                className="cursor-pointer"
                onClick={() => setSelectedId((prev) => (prev === edge.id ? null : edge.id))}
                onMouseEnter={() => setHoverId(edge.id)}
                onMouseLeave={() => setHoverId((prev) => (prev === edge.id ? null : prev))}
              >
                <path
                  d={edgePath(from, to)}
                  fill="none"
                  stroke="transparent"
                  strokeWidth="14"
                />
                <path
                  d={edgePath(from, to)}
                  fill="none"
                  className={cn(
                    active ? 'stroke-brand' : 'stroke-tech',
                    dimmed && 'opacity-25',
                  )}
                  strokeWidth={active ? 2.5 : 1.6}
                  markerEnd={active ? 'url(#schema-arrow-active)' : 'url(#schema-arrow)'}
                  strokeDasharray={edge.from !== 'enterprise_basic' ? '5 4' : undefined}
                />
              </g>
            )
          })}

          {/* 节点 */}
          {nodes.map((name) => {
            const p = positions.get(name)
            if (!p) return null
            const isHub = edges.filter((e) => e.from === name).length >= 2
            const related = focusNode === name
              || activeEdge?.from === name
              || activeEdge?.to === name
            const dimmed = (highlightId != null || focusNode != null) && !related
            return (
              <g
                key={name}
                transform={`translate(${p.x - NODE_W / 2}, ${p.y - NODE_H / 2})`}
                className="cursor-pointer"
                onClick={() => {
                  setFocusNode((prev) => (prev === name ? null : name))
                  setSelectedId(null)
                }}
                onMouseEnter={() => setFocusNode(name)}
              >
                <rect
                  width={NODE_W}
                  height={NODE_H}
                  rx={12}
                  className={cn(
                    isHub ? 'fill-brand-soft stroke-brand' : 'fill-card stroke-tech/50',
                    dimmed && 'opacity-30',
                  )}
                  strokeWidth={isHub || related ? 2 : 1.25}
                  style={related && !isHub ? { filter: 'drop-shadow(0 0 8px rgb(14 116 144 / 0.35))' } : undefined}
                />
                <text
                  x={NODE_W / 2}
                  y={NODE_H / 2 + 4}
                  textAnchor="middle"
                  className="fill-foreground text-[12px] font-semibold"
                >
                  {displayName(name)}
                </text>
              </g>
            )
          })}
        </svg>
      </div>

      <div className="shrink-0 rounded-xl border border-border/80 bg-card/80 px-4 py-3 text-xs shadow-[inset_0_1px_0_rgb(255_255_255/0.55)]">
        {activeEdge ? (
          <div className="space-y-1">
            <p className="font-medium">
              <span className="text-brand">{displayName(activeEdge.from)}</span>
              <span className="mx-2 text-muted-foreground">→</span>
              <span className="text-tech">{displayName(activeEdge.to)}</span>
            </p>
            {activeEdge.note && <p className="text-foreground">{activeEdge.note}</p>}
          </div>
        ) : (
          <p className="text-muted-foreground">
            悬停或点击连线查看关联说明；虚线表示维度之间的业务关联（不直接挂在企业下）。
          </p>
        )}
      </div>
    </div>
  )
}
