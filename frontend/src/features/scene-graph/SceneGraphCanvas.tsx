import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts";
import type { ECharts, EChartsOption } from "echarts";

type RawNode = Record<string, unknown>;
type RawEdge = Record<string, unknown>;

interface SceneGraphCanvasProps {
  nodes: RawNode[];
  edges: RawEdge[];
  memoryNodes?: RawNode[];
  selectedNodeId?: string;
  onSelectNode?: (nodeId: string) => void;
}

interface TopologyNode {
  id: string;
  name: string;
  value: string;
  category: string;
  symbolSize: number;
  itemStyle: {
    color: string;
    borderColor?: string;
    borderWidth?: number;
    opacity?: number;
  };
  tooltip: {
    formatter: string;
  };
  raw: RawNode;
}

interface TopologyLink {
  source: string;
  target: string;
  value: number;
  label: {
    show: boolean;
    formatter: string;
  };
  tooltip: {
    formatter: string;
  };
  lineStyle: {
    width: number;
    opacity: number;
    color: string;
    curveness: number;
  };
}

const NODE_COLORS: Record<string, string> = {
  room: "#6da544",
  robot: "#d94a64",
  human: "#d94a64",
  movable_object: "#5470c6",
  fixed_object: "#91cc75",
  control_object: "#fac858",
  furniture: "#73c0de",
  appliance: "#3ba272",
  container: "#fc8452",
  door: "#ee6666",
  button: "#9a60b4",
};

const LINK_COLORS: Record<string, string> = {
  supports: "#2f9e75",
  supported_by: "#3b82f6",
  touching_or_adjacent: "#94a3b8",
  connected: "#2f9e75",
  connected_to: "#2f9e75",
  doorway: "#ef4444",
  controls: "#f59e0b",
  contains: "#64748b",
  inside_room: "#64748b",
  in: "#3b82f6",
  at: "#3b82f6",
  on: "#3b82f6",
  near: "#94a3b8",
};

function text(value: unknown): string {
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

function html(value: string): string {
  return value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

function nodePayload(node: RawNode): RawNode {
  const properties = node.properties;
  return properties && typeof properties === "object" && !Array.isArray(properties) ? (properties as RawNode) : node;
}

function nodeId(node: RawNode): string {
  return text(node.id) || text(node.node_key);
}

function nodeType(node: RawNode): string {
  const payload = nodePayload(node);
  return text(payload.node_type || payload.type || node.node_type);
}

function semanticType(node: RawNode): string {
  const payload = nodePayload(node);
  return text(payload.semantic_type || payload.object_type || node.semantic_type);
}

function nodeLabel(node: RawNode): string {
  const payload = nodePayload(node);
  return text(payload.name_cn || payload.name || payload.id || node.id);
}

function nodeCategory(node: RawNode): string {
  const type = nodeType(node);
  const semantic = semanticType(node);
  if (semantic in NODE_COLORS) {
    return semantic;
  }
  return type || semantic || "object";
}

function parentId(node: RawNode): string {
  const payload = nodePayload(node);
  return text(payload.parent);
}

function visualCues(node: RawNode): string[] {
  const payload = nodePayload(node);
  return Array.isArray(payload.visual_cues)
    ? payload.visual_cues.filter((cue): cue is string => typeof cue === "string")
    : [];
}

function edgeSource(edge: RawEdge): string {
  return text(edge.source_id || edge.source);
}

function edgeTarget(edge: RawEdge): string {
  return text(edge.target_id || edge.target);
}

function edgeRelation(edge: RawEdge): string {
  return text(edge.relation || edge.edge_type || edge.value);
}

function edgeDistance(edge: RawEdge): string {
  const properties = edge.properties;
  const payload = properties && typeof properties === "object" && !Array.isArray(properties) ? (properties as RawEdge) : edge;
  const distance = payload.distance ?? payload.dist;
  return typeof distance === "number" ? `${distance.toFixed(4)}m` : text(distance);
}

function nodeColor(category: string): string {
  return NODE_COLORS[category] ?? "#5470c6";
}

function linkColor(relation: string): string {
  return LINK_COLORS[relation] ?? "#94a3b8";
}

function degreeByNode(nodes: RawNode[], edges: RawEdge[]): Map<string, number> {
  const degrees = new Map(nodes.map((node) => [nodeId(node), 0]));
  for (const edge of edges) {
    const source = edgeSource(edge);
    const target = edgeTarget(edge);
    if (degrees.has(source)) {
      degrees.set(source, (degrees.get(source) ?? 0) + 1);
    }
    if (degrees.has(target)) {
      degrees.set(target, (degrees.get(target) ?? 0) + 1);
    }
  }
  return degrees;
}

function shouldShowNode(node: RawNode): boolean {
  const type = nodeType(node);
  return Boolean(nodeId(node)) && type !== "floor";
}

function buildTopology(nodes: RawNode[], edges: RawEdge[], memoryNodes: RawNode[], relationFilter: string) {
  const memoryIds = new Set(memoryNodes.map(nodeId));
  const merged = [...nodes, ...memoryNodes].filter(shouldShowNode);
  const nodeIds = new Set(merged.map(nodeId));
  const visibleEdges = edges.filter((edge) => {
    const relation = edgeRelation(edge);
    return (
      edgeSource(edge) &&
      edgeTarget(edge) &&
      nodeIds.has(edgeSource(edge)) &&
      nodeIds.has(edgeTarget(edge)) &&
      (!relationFilter || relation === relationFilter)
    );
  });
  const degrees = degreeByNode(merged, visibleEdges);
  const labelById = new Map(merged.map((node) => [nodeId(node), nodeLabel(node)]));
  const topologyNodes: TopologyNode[] = merged.map((node) => {
    const id = nodeId(node);
    const category = nodeCategory(node);
    const semantic = semanticType(node);
    const type = nodeType(node);
    const degree = degrees.get(id) ?? 0;
    const room = type === "room" || semantic === "room" || category === "room";
    const memory = memoryIds.has(id);
    const parent = parentId(node);
    const cues = visualCues(node);
    const broken = cues.includes("broken");
    const running = cues.includes("running_pulse");
    const wet = cues.includes("water_droplets");
    const drying = cues.includes("drying_bubbles");
    const hot = cues.includes("steam");
    const falling = cues.includes("falling");
    return {
      id,
      name: nodeLabel(node),
      value: semantic || type,
      category,
      symbolSize: room
        ? Math.max(24, Math.min(34, 22 + Math.sqrt(degree + 1) * 3))
        : Math.max(10, Math.min(24, 10 + Math.sqrt(degree + 1) * 3)),
      itemStyle: {
        color: broken ? "#dc2626" : nodeColor(category),
        borderColor: broken ? "#991b1b" : falling ? "#7c3aed" : running ? "#f59e0b" : hot ? "#ea580c" : drying ? "#ca8a04" : wet ? "#0891b2" : memory ? "#94a3b8" : "#ffffff",
        borderWidth: broken || falling || running || hot || drying || wet || memory ? 2 : 1,
        opacity: memory ? 0.55 : 1,
      },
      tooltip: {
        formatter: [
          `<b>${html(nodeLabel(node))}</b>`,
          `id: ${html(id)}`,
          `type: ${html(type || "-")}`,
          `semantic: ${html(semantic || "-")}`,
          parent ? `parent: ${html(parent)}` : "",
          cues.length ? `status: ${html(cues.join(", "))}` : "",
          `degree: ${degree}`,
        ]
          .filter(Boolean)
          .join("<br/>"),
      },
      raw: node,
    };
  });
  const topologyLinks: TopologyLink[] = visibleEdges.map((edge) => {
    const source = edgeSource(edge);
    const target = edgeTarget(edge);
    const relation = edgeRelation(edge) || "related";
    const distance = edgeDistance(edge);
    return {
      source,
      target,
      value: 1,
      label: {
        show: true,
        formatter: relation,
      },
      tooltip: {
        formatter: [
          `${html(labelById.get(source) ?? source)} -> ${html(labelById.get(target) ?? target)}`,
          html(relation),
          distance ? `distance: ${html(distance)}` : "",
        ]
          .filter(Boolean)
          .join("<br/>"),
      },
      lineStyle: {
        width: relation === "controls" || relation === "supports" ? 1.8 : 1.35,
        opacity: 0.62,
        color: linkColor(relation),
        curveness: relation === "controls" ? 0.08 : 0.02,
      },
    };
  });
  return { topologyNodes, topologyLinks };
}

function relationTypes(edges: RawEdge[]): string[] {
  return Array.from(new Set(edges.map(edgeRelation).filter(Boolean))).sort();
}

export function SceneGraphCanvas({ nodes, edges, memoryNodes = [], selectedNodeId = "", onSelectNode }: SceneGraphCanvasProps) {
  const chartRef = useRef<HTMLDivElement | null>(null);
  const chartInstance = useRef<ECharts | null>(null);
  const [relationFilter, setRelationFilter] = useState("");
  const [query, setQuery] = useState("");
  const relations = useMemo(() => relationTypes(edges), [edges]);
  const searchedNodeId = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) {
      return "";
    }
    const match = [...nodes, ...memoryNodes].find((node) => {
      return nodeId(node).toLowerCase().includes(normalized) || nodeLabel(node).toLowerCase().includes(normalized);
    });
    return match ? nodeId(match) : "";
  }, [memoryNodes, nodes, query]);
  const activeNodeId = searchedNodeId || selectedNodeId;
  const { topologyNodes, topologyLinks } = useMemo(
    () => buildTopology(nodes, edges, memoryNodes, relationFilter),
    [edges, memoryNodes, nodes, relationFilter],
  );

  useEffect(() => {
    if (!chartRef.current) {
      return;
    }
    if (!chartInstance.current) {
      chartInstance.current = echarts.init(chartRef.current, undefined, { renderer: "canvas" });
    }
    const chart = chartInstance.current;
    const option: EChartsOption = {
      backgroundColor: "#ffffff",
      tooltip: {
        trigger: "item",
        confine: true,
        borderWidth: 1,
        borderColor: "#d4d4d8",
        backgroundColor: "rgba(255, 255, 255, 0.96)",
        textStyle: {
          color: "#111827",
          fontSize: 12,
        },
      },
      series: [
        {
          type: "graph",
          layout: "force",
          top: 68,
          right: 34,
          bottom: 34,
          left: 34,
          roam: true,
          zoom: 0.72,
          scaleLimit: {
            min: 0.25,
            max: 4,
          },
          draggable: true,
          data: topologyNodes,
          links: topologyLinks,
          categories: Array.from(new Set(topologyNodes.map((node) => node.category))).map((name) => ({ name })),
          force: {
            repulsion: 170,
            edgeLength: [42, 130],
            gravity: 0.18,
            friction: 0.62,
            layoutAnimation: true,
          },
          label: {
            show: true,
            position: "right",
            fontSize: 10,
            color: "#27272a",
            formatter: "{b}",
          },
          edgeSymbol: ["none", "arrow"],
          edgeSymbolSize: 5,
          edgeLabel: {
            show: true,
            fontSize: 9,
            color: "#52525b",
          },
          lineStyle: {
            width: 1.5,
            opacity: 0.65,
            color: "#94a3b8",
          },
          emphasis: {
            focus: "adjacency",
            lineStyle: {
              width: 3,
              opacity: 0.9,
            },
            label: {
              show: true,
              fontWeight: 700,
            },
          },
        },
      ],
    };
    chart.setOption(option, true);
    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
    };
  }, [topologyLinks, topologyNodes]);

  useEffect(() => {
    const chart = chartInstance.current;
    if (!chart) {
      return;
    }
    const handleClick = (params: unknown) => {
      const payload = params as { dataType?: string; data?: { id?: string } };
      if (payload.dataType === "node" && payload.data?.id) {
        onSelectNode?.(payload.data.id);
      }
    };
    chart.off("click");
    chart.on("click", handleClick);
    return () => {
      chart.off("click", handleClick);
    };
  }, [onSelectNode]);

  useEffect(() => {
    const chart = chartInstance.current;
    if (!chart || !activeNodeId) {
      return;
    }
    const index = topologyNodes.findIndex((node) => node.id === activeNodeId);
    if (index >= 0) {
      chart.dispatchAction({ type: "downplay", seriesIndex: 0 });
      chart.dispatchAction({ type: "highlight", seriesIndex: 0, dataIndex: index });
      chart.dispatchAction({ type: "showTip", seriesIndex: 0, dataIndex: index });
    }
  }, [activeNodeId, topologyNodes]);

  useEffect(() => {
    return () => {
      chartInstance.current?.dispose();
      chartInstance.current = null;
    };
  }, []);

  return (
    <div className="semantic-topology">
      <div className="topology-toolbar">
        <div className="topology-stats">
          <strong>Semantic Topology</strong>
          <span>{topologyNodes.length} nodes</span>
          <span>{topologyLinks.length} edges</span>
        </div>
        <div className="topology-controls">
          <input
            className="topology-search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search node"
          />
          <select value={relationFilter} onChange={(event) => setRelationFilter(event.target.value)}>
            <option value="">All relations</option>
            {relations.map((relation) => (
              <option key={relation} value={relation}>
                {relation}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div ref={chartRef} className="topology-chart" />
      <div className="topology-hint">drag nodes · wheel zoom · hover for details</div>
    </div>
  );
}
