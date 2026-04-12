import { useMemo } from 'react'
import ReactFlow, {
  Background,
  Controls,
  Edge,
  Node,
  Position,
  Handle,
  NodeProps,
} from 'reactflow'
import dagre from 'dagre'
import { AlertCircle, CheckCircle2, Database } from 'lucide-react'
import type { Lineage } from '@/lib/types'
import { cn } from '@/lib/utils'

// ── Auto-layout helper ───────────────────────────────────────────────────────
// React Flow doesn't layout nodes for you.  We use dagre to compute
// x/y positions for a left-to-right DAG, then convert to RF format.

function layoutGraph(nodes: Node[], edges: Edge[]) {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'LR', nodesep: 40, ranksep: 80, marginx: 20, marginy: 20 })

  const NODE_W = 200
  const NODE_H = 72

  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }))
  edges.forEach((e) => g.setEdge(e.source, e.target))

  dagre.layout(g)

  return {
    nodes: nodes.map((n) => {
      const pos = g.node(n.id)
      return {
        ...n,
        position: { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 },
        targetPosition: Position.Left,
        sourcePosition: Position.Right,
      }
    }),
    edges,
  }
}

// ── Custom node component ────────────────────────────────────────────────────

interface ModelNodeData {
  label: string
  state: 'healthy' | 'upstream' | 'broken' | 'fixed' | 'downstream'
}

function ModelNode({ data }: NodeProps<ModelNodeData>) {
  const configs = {
    healthy: {
      bg: 'bg-white',
      border: 'border-slate-200',
      iconBg: 'bg-slate-100 text-slate-600',
      icon: Database,
      label: 'Model',
      labelColor: 'text-slate-500',
    },
    upstream: {
      bg: 'bg-white',
      border: 'border-violet-200',
      iconBg: 'bg-violet-100 text-violet-600',
      icon: Database,
      label: 'Upstream',
      labelColor: 'text-violet-600',
    },
    broken: {
      bg: 'bg-rose-50',
      border: 'border-rose-300',
      iconBg: 'bg-rose-100 text-rose-600',
      icon: AlertCircle,
      label: 'Broken',
      labelColor: 'text-rose-600',
    },
    fixed: {
      bg: 'bg-emerald-50',
      border: 'border-emerald-300',
      iconBg: 'bg-emerald-100 text-emerald-600',
      icon: CheckCircle2,
      label: 'Fixed',
      labelColor: 'text-emerald-600',
    },
    downstream: {
      bg: 'bg-white',
      border: 'border-blue-200',
      iconBg: 'bg-blue-100 text-blue-600',
      icon: Database,
      label: 'Downstream',
      labelColor: 'text-blue-600',
    },
  } as const

  const cfg = configs[data.state]
  const Icon = cfg.icon

  return (
    <div
      className={cn(
        'rounded-xl border-2 shadow-sm min-w-[180px] px-3 py-2.5 flex items-center gap-3',
        cfg.bg,
        cfg.border,
      )}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!bg-slate-300 !border-slate-300 !w-2 !h-2"
      />
      <div
        className={cn(
          'w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0',
          cfg.iconBg,
        )}
      >
        <Icon className="w-4 h-4" />
      </div>
      <div className="min-w-0">
        <div
          className={cn(
            'text-[9px] font-bold uppercase tracking-wider',
            cfg.labelColor,
          )}
        >
          {cfg.label}
        </div>
        <div className="text-[13px] font-semibold text-slate-900 truncate">
          {data.label}
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        className="!bg-slate-300 !border-slate-300 !w-2 !h-2"
      />
    </div>
  )
}

const nodeTypes = { model: ModelNode }

// ── Main component ───────────────────────────────────────────────────────────

interface Props {
  lineage: Lineage
  brokenModel: string
  queryIsValid: boolean
}

export function LineageGraph({ lineage, brokenModel, queryIsValid }: Props) {
  const { nodes, edges } = useMemo(() => {
    if (!lineage.nodes || lineage.nodes.length === 0) {
      return { nodes: [], edges: [] }
    }

    const upstreamSet = new Set(lineage.upstream || [])
    const downstreamSet = new Set(lineage.downstream || [])

    const rawNodes: Node[] = lineage.nodes.map((name) => {
      let state: ModelNodeData['state'] = 'healthy'
      if (name === brokenModel) {
        state = queryIsValid ? 'fixed' : 'broken'
      } else if (upstreamSet.has(name)) {
        state = 'upstream'
      } else if (downstreamSet.has(name)) {
        state = 'downstream'
      }
      return {
        id: name,
        type: 'model',
        position: { x: 0, y: 0 },
        data: { label: name, state },
      }
    })

    const rawEdges: Edge[] = (lineage.edges || []).map((e, i) => ({
      id: `e-${i}`,
      source: e.from,
      target: e.to,
      type: 'smoothstep',
      animated: e.to === brokenModel && !queryIsValid,
      style: {
        stroke: e.to === brokenModel && !queryIsValid ? '#f43f5e' : '#cbd5e1',
        strokeWidth: 2,
      },
    }))

    return layoutGraph(rawNodes, rawEdges)
  }, [lineage, brokenModel, queryIsValid])

  if (nodes.length === 0) {
    return (
      <div className="h-96 flex items-center justify-center text-slate-400 text-sm">
        No lineage data
      </div>
    )
  }

  return (
    <div className="h-[420px] w-full bg-slate-50 rounded-lg border border-slate-200">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
        defaultViewport={{ x: 0, y: 0, zoom: 1 }}
        minZoom={0.5}
        maxZoom={1.5}
        nodesDraggable={false}
        nodesConnectable={false}
      >
        <Background color="#e2e8f0" gap={16} size={1} />
        <Controls
          showInteractive={false}
          className="!bg-white !border !border-slate-200 !rounded-lg !shadow-sm"
        />
      </ReactFlow>
    </div>
  )
}
