import React, { useState, useMemo } from "react";
import { GraphNode, GraphEdge } from "../types";
import { ZoomIn, ZoomOut, RotateCcw, Filter, Search, ShieldAlert, Users, Building2, Info, ChevronRight } from "lucide-react";

interface EvidenceEdge {
  source: string;
  target: string;
  relation: string;
  evidence_sentence: string;
}

interface NetworkGraphVisualizerProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  evidenceEdges?: EvidenceEdge[];
  companyName: string;
}

interface LayoutNode extends GraphNode {
  x: number;
  y: number;
  isShell: boolean;
  degree: number;
}

export const NetworkGraphVisualizer: React.FC<NetworkGraphVisualizerProps> = ({
  nodes,
  edges,
  evidenceEdges = [],
  companyName,
}) => {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [filterType, setFilterType] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Dimensions of SVG canvas
  const width = 800;
  const height = 550;
  const centerX = width / 2;
  const centerY = height / 2;

  // Process nodes and calculate layout
  const { layoutNodes, nodeMap, shellCount, officerCount, entityCount } = useMemo(() => {
    // Degree map
    const degMap: Record<string, number> = {};
    edges.forEach((e) => {
      degMap[e.source] = (degMap[e.source] || 0) + 1;
      degMap[e.target] = (degMap[e.target] || 0) + 1;
    });

    let sCount = 0;
    let oCount = 0;
    let eCount = 0;

    const focalNode = nodes.find((n) => n.type === "FOCAL_COMPANY") || nodes[0];
    const otherNodes = nodes.filter((n) => n.id !== focalNode?.id);

    // Group remaining nodes
    const officers: GraphNode[] = [];
    const shells: GraphNode[] = [];
    const regular: GraphNode[] = [];

    otherNodes.forEach((n) => {
      const isShell =
        n.type === "SHELL_OR_HOLDING" ||
        n.label.toLowerCase().includes("llc") ||
        n.label.toLowerCase().includes("holding") ||
        n.label.toLowerCase().includes("l.p.") ||
        n.label.toLowerCase().includes("lp");

      if (isShell) {
        shells.push(n);
        sCount++;
      } else if (n.type === "PERSON" || n.label.toLowerCase().includes("officer")) {
        officers.push(n);
        oCount++;
      } else {
        regular.push(n);
        eCount++;
      }
    });

    const lNodes: LayoutNode[] = [];

    // Place focal node at center
    if (focalNode) {
      lNodes.push({
        ...focalNode,
        x: centerX,
        y: centerY,
        isShell: false,
        degree: degMap[focalNode.id] || degMap[focalNode.label] || 0,
      });
    }

    // Place officers in inner orbit (radius ~130)
    const rInner = 140;
    officers.forEach((n, idx) => {
      const angle = (idx / Math.max(officers.length, 1)) * 2 * Math.PI - Math.PI / 2;
      lNodes.push({
        ...n,
        x: centerX + rInner * Math.cos(angle),
        y: centerY + rInner * Math.sin(angle),
        isShell: false,
        degree: degMap[n.id] || degMap[n.label] || 0,
      });
    });

    // Place regular entities in middle orbit (radius ~210)
    const rMid = 210;
    regular.forEach((n, idx) => {
      const angle = (idx / Math.max(regular.length, 1)) * 2 * Math.PI + Math.PI / 4;
      lNodes.push({
        ...n,
        x: centerX + rMid * Math.cos(angle),
        y: centerY + rMid * Math.sin(angle),
        isShell: false,
        degree: degMap[n.id] || degMap[n.label] || 0,
      });
    });

    // Place shells in outer ring (radius ~260) with warning emphasis
    const rOuter = 265;
    shells.forEach((n, idx) => {
      const angle = (idx / Math.max(shells.length, 1)) * 2 * Math.PI - Math.PI / 3;
      lNodes.push({
        ...n,
        x: centerX + rOuter * Math.cos(angle),
        y: centerY + rOuter * Math.sin(angle),
        isShell: true,
        degree: degMap[n.id] || degMap[n.label] || 0,
      });
    });

    const nMap: Record<string, LayoutNode> = {};
    lNodes.forEach((n) => {
      nMap[n.id] = n;
      nMap[n.label] = n; // also fallback to label
    });

    return {
      layoutNodes: lNodes,
      nodeMap: nMap,
      shellCount: sCount,
      officerCount: oCount,
      entityCount: eCount,
    };
  }, [nodes, edges, centerX, centerY]);

  // Selected node
  const selectedNode = useMemo(() => {
    if (!selectedNodeId) return null;
    return layoutNodes.find((n) => n.id === selectedNodeId || n.label === selectedNodeId) || null;
  }, [selectedNodeId, layoutNodes]);

  // Connected edges for selected node
  const connectedEdges = useMemo(() => {
    if (!selectedNode) return [];
    const sid = selectedNode.id;
    const slabel = selectedNode.label;
    return edges.filter(
      (e) => e.source === sid || e.target === sid || e.source === slabel || e.target === slabel
    );
  }, [selectedNode, edges]);

  // Evidence sentences matching the selected node or all
  const relevantEvidence = useMemo(() => {
    if (!selectedNode) return evidenceEdges.slice(0, 5);
    const sid = selectedNode.id.toLowerCase();
    const slabel = selectedNode.label.toLowerCase();
    return evidenceEdges.filter(
      (e) =>
        e.source.toLowerCase().includes(sid) ||
        e.target.toLowerCase().includes(sid) ||
        e.source.toLowerCase().includes(slabel) ||
        e.target.toLowerCase().includes(slabel)
    );
  }, [selectedNode, evidenceEdges]);

  // Handle pan drag
  const handleMouseDown = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).tagName === "svg" || (e.target as HTMLElement).tagName === "rect") {
      setIsDragging(true);
      setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDragging) {
      setPan({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y });
    }
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  // Node filtering
  const visibleNodes = useMemo(() => {
    return layoutNodes.filter((n) => {
      if (filterQueryMatches(n, searchQuery) === false) return false;
      if (filterType === "ALL") return true;
      if (filterType === "SHELL") return n.isShell;
      if (filterType === "OFFICER") return n.type === "PERSON";
      if (filterType === "ENTITY") return !n.isShell && n.type !== "PERSON" && n.type !== "FOCAL_COMPANY";
      return true;
    });
  }, [layoutNodes, filterType, searchQuery]);

  function filterQueryMatches(n: LayoutNode, q: string): boolean {
    if (!q) return true;
    const lower = q.toLowerCase();
    return n.label.toLowerCase().includes(lower) || n.id.toLowerCase().includes(lower);
  }

  const visibleNodeIds = useMemo(() => new Set(visibleNodes.map((n) => n.id)), [visibleNodes]);

  return (
    <div className="space-y-4">
      {/* 1. Control Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3 bg-white border border-slate-200 rounded-lg shadow-sm text-xs">
        {/* Filters */}
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-slate-400 font-medium flex items-center mr-1">
            <Filter className="w-3.5 h-3.5 mr-1" /> View:
          </span>
          {[
            { id: "ALL", label: `All (${nodes.length})` },
            { id: "SHELL", label: `Shell / LLCs (${shellCount})`, color: "text-rose-700 bg-rose-50 border-rose-200" },
            { id: "OFFICER", label: `Officers (${officerCount})`, color: "text-indigo-700 bg-indigo-50 border-indigo-200" },
            { id: "ENTITY", label: `Affiliates (${entityCount})`, color: "text-emerald-700 bg-emerald-50 border-emerald-200" },
          ].map((btn) => (
            <button
              key={btn.id}
              onClick={() => setFilterType(btn.id)}
              className={`px-2.5 py-1 rounded-md border font-medium transition-colors ${
                filterType === btn.id
                  ? "bg-sky-600 text-white border-sky-600"
                  : btn.color || "bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100"
              }`}
            >
              {btn.label}
            </button>
          ))}
        </div>

        {/* Search & Zoom Controls */}
        <div className="flex items-center space-x-2">
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-2 text-slate-400" />
            <input
              type="text"
              placeholder="Search entity..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 pr-2.5 py-1 w-36 text-xs bg-slate-50 border border-slate-200 rounded focus:w-48 focus:bg-white focus:outline-none focus:ring-1 focus:ring-sky-500 transition-all"
            />
          </div>

          <div className="flex items-center space-x-1 border-l border-slate-200 pl-2">
            <button
              onClick={() => setZoom((z) => Math.min(z + 0.15, 2.2))}
              className="p-1 rounded bg-slate-100 text-slate-600 hover:bg-slate-200"
              title="Zoom In"
            >
              <ZoomIn className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setZoom((z) => Math.max(z - 0.15, 0.5))}
              className="p-1 rounded bg-slate-100 text-slate-600 hover:bg-slate-200"
              title="Zoom Out"
            >
              <ZoomOut className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => {
                setZoom(1);
                setPan({ x: 0, y: 0 });
                setSelectedNodeId(null);
                setSearchQuery("");
                setFilterType("ALL");
              }}
              className="p-1 rounded bg-slate-100 text-slate-600 hover:bg-slate-200"
              title="Reset View"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* 2. Visual Graph Area & Side Inspection Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* Interactive SVG Canvas */}
        <div className="lg:col-span-3 bg-slate-950 rounded-lg border border-slate-800 overflow-hidden relative shadow-inner">
          {/* Legend Banner */}
          <div className="absolute top-3 left-3 z-10 flex flex-wrap items-center gap-3 bg-slate-900/80 backdrop-blur-md px-3 py-1.5 rounded-md border border-slate-700/60 text-[11px] text-slate-300">
            <div className="flex items-center space-x-1.5">
              <span className="w-3 h-3 rounded-full bg-sky-500 ring-2 ring-sky-400/40"></span>
              <span>Focal Registrant</span>
            </div>
            <div className="flex items-center space-x-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-indigo-400"></span>
              <span>Executive / Officer</span>
            </div>
            <div className="flex items-center space-x-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
              <span>Affiliate / Related</span>
            </div>
            <div className="flex items-center space-x-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-pulse"></span>
              <span className="text-rose-300 font-semibold">Shell / Holding LLC</span>
            </div>
          </div>

          <div className="absolute bottom-3 right-3 z-10 bg-slate-900/80 backdrop-blur-md px-2.5 py-1 rounded text-[10px] text-slate-400 border border-slate-800">
            Click node to inspect • Drag to pan • Scroll to zoom
          </div>

          <svg
            width="100%"
            height={height}
            viewBox={`0 0 ${width} ${height}`}
            className="cursor-grab active:cursor-grabbing select-none"
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
          >
            {/* Background grid */}
            <defs>
              <pattern id="grid" width="30" height="30" patternUnits="userSpaceOnUse">
                <circle cx="15" cy="15" r="0.8" fill="#334155" opacity="0.4" />
              </pattern>
              <radialGradient id="focalGlow" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="#0284c7" stopOpacity="0.4" />
                <stop offset="100%" stopColor="#0284c7" stopOpacity="0" />
              </radialGradient>
            </defs>
            <rect width={width} height={height} fill="#090d16" />
            <rect width={width} height={height} fill="url(#grid)" />

            <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
              {/* Radial Orbit Guide Rings */}
              <circle cx={centerX} cy={centerY} r={140} fill="none" stroke="#1e293b" strokeDasharray="3 4" strokeWidth="1" />
              <circle cx={centerX} cy={centerY} r={210} fill="none" stroke="#1e293b" strokeDasharray="3 4" strokeWidth="1" />
              <circle cx={centerX} cy={centerY} r={265} fill="none" stroke="#334155" strokeDasharray="2 4" strokeWidth="1" />

              {/* Edge lines */}
              {edges.map((e, idx) => {
                const src = nodeMap[e.source] || nodeMap[e.source.toLowerCase()];
                const tgt = nodeMap[e.target] || nodeMap[e.target.toLowerCase()];
                if (!src || !tgt) return null;

                const isConnectedToSelected =
                  selectedNode &&
                  (src.id === selectedNode.id || tgt.id === selectedNode.id || src.label === selectedNode.label || tgt.label === selectedNode.label);

                const isMuted = selectedNode && !isConnectedToSelected;

                let strokeColor = "#334155";
                let strokeWidth = 1.2;

                if (isConnectedToSelected) {
                  strokeColor = "#38bdf8";
                  strokeWidth = 2.4;
                } else if (src.isShell || tgt.isShell) {
                  strokeColor = "#e11d4860";
                  strokeWidth = 1.6;
                }

                return (
                  <g key={idx} opacity={isMuted ? 0.15 : 0.85}>
                    <line
                      x1={src.x}
                      y1={src.y}
                      x2={tgt.x}
                      y2={tgt.y}
                      stroke={strokeColor}
                      strokeWidth={strokeWidth}
                    />
                  </g>
                );
              })}

              {/* Focal Glow */}
              <circle cx={centerX} cy={centerY} r={70} fill="url(#focalGlow)" />

              {/* Nodes */}
              {layoutNodes.map((n) => {
                const isSelected = selectedNode && (selectedNode.id === n.id || selectedNode.label === n.label);
                const isVisible = visibleNodeIds.has(n.id);
                const isFocal = n.type === "FOCAL_COMPANY" || n.label === companyName;

                let r = 8;
                let fill = "#10b981"; // emerald for entity
                let stroke = "#059669";

                if (isFocal) {
                  r = 18;
                  fill = "#0284c7";
                  stroke = "#38bdf8";
                } else if (n.isShell) {
                  r = 10;
                  fill = "#f43f5e";
                  stroke = "#be123c";
                } else if (n.type === "PERSON") {
                  r = 8;
                  fill = "#6366f1";
                  stroke = "#4338ca";
                }

                if (isSelected) {
                  stroke = "#ffffff";
                }

                const opacity = !isVisible ? 0.12 : selectedNode && !isSelected ? 0.45 : 1;

                return (
                  <g
                    key={n.id}
                    className="cursor-pointer transition-all duration-150"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedNodeId(n.id === selectedNodeId ? null : n.id);
                    }}
                    opacity={opacity}
                  >
                    {/* Shell pulse ring */}
                    {n.isShell && (
                      <circle
                        cx={n.x}
                        cy={n.y}
                        r={r + 5}
                        fill="none"
                        stroke="#f43f5e"
                        strokeWidth="1.5"
                        strokeDasharray="2 3"
                        opacity={0.7}
                      />
                    )}

                    {/* Node circle */}
                    <circle
                      cx={n.x}
                      cy={n.y}
                      r={isSelected ? r + 3 : r}
                      fill={fill}
                      stroke={stroke}
                      strokeWidth={isSelected ? 3 : 1.5}
                    />

                    {/* Text Label */}
                    <text
                      x={n.x}
                      y={n.y + (isFocal ? 28 : r + 11)}
                      textAnchor="middle"
                      fill={isSelected ? "#ffffff" : isFocal ? "#38bdf8" : n.isShell ? "#fca5a5" : "#94a3b8"}
                      fontSize={isFocal ? "11px" : isSelected ? "10px" : "9px"}
                      fontWeight={isFocal || isSelected || n.isShell ? "600" : "400"}
                      className="pointer-events-none drop-shadow-sm"
                    >
                      {n.label.length > 20 ? n.label.slice(0, 18) + "..." : n.label}
                    </text>
                  </g>
                );
              })}
            </g>
          </svg>
        </div>

        {/* 3. Node Detail Inspector Panel */}
        <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm flex flex-col justify-between text-xs space-y-4">
          <div>
            <div className="flex items-center justify-between pb-2 border-b border-slate-200">
              <h4 className="font-semibold text-slate-800 flex items-center">
                <Info className="w-3.5 h-3.5 mr-1 text-sky-600" /> Entity Inspector
              </h4>
              {selectedNode && (
                <button
                  onClick={() => setSelectedNodeId(null)}
                  className="text-[10px] text-slate-400 hover:text-slate-700"
                >
                  Clear Selection
                </button>
              )}
            </div>

            {selectedNode ? (
              <div className="mt-3 space-y-3">
                <div>
                  <span className="text-[10px] uppercase tracking-wider text-slate-400 font-bold block">
                    Entity Name
                  </span>
                  <div className="font-bold text-slate-900 text-sm mt-0.5">{selectedNode.label}</div>
                  <div className="text-[10px] font-mono text-slate-400 mt-0.5">ID: {selectedNode.id}</div>
                </div>

                <div>
                  <span className="text-[10px] uppercase tracking-wider text-slate-400 font-bold block mb-1">
                    Classification
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {selectedNode.type === "FOCAL_COMPANY" && (
                      <span className="px-2 py-0.5 rounded bg-sky-100 text-sky-800 font-semibold text-[10px]">
                        Focal Registrant
                      </span>
                    )}
                    {selectedNode.type === "PERSON" && (
                      <span className="px-2 py-0.5 rounded bg-indigo-100 text-indigo-800 font-semibold text-[10px]">
                        Officer / Director
                      </span>
                    )}
                    {selectedNode.isShell && (
                      <span className="px-2 py-0.5 rounded bg-rose-100 text-rose-800 font-bold text-[10px] flex items-center">
                        <ShieldAlert className="w-3 h-3 mr-1" /> Shell / LLC Entity
                      </span>
                    )}
                    {!selectedNode.isShell && selectedNode.type !== "PERSON" && selectedNode.type !== "FOCAL_COMPANY" && (
                      <span className="px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 font-medium text-[10px]">
                        Related Affiliate
                      </span>
                    )}
                  </div>
                </div>

                <div>
                  <span className="text-[10px] uppercase tracking-wider text-slate-400 font-bold block mb-1">
                    Direct Connections ({connectedEdges.length})
                  </span>
                  {connectedEdges.length > 0 ? (
                    <div className="space-y-1.5 max-h-36 overflow-y-auto pr-1">
                      {connectedEdges.map((e, idx) => (
                        <div key={idx} className="p-1.5 rounded bg-slate-50 border border-slate-100 text-[11px]">
                          <div className="font-medium text-slate-700 truncate">
                            {e.source === selectedNode.id ? e.target : e.source}
                          </div>
                          <div className="text-[9px] text-sky-600 font-mono uppercase">{e.relation}</div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-[11px] text-slate-400 italic">No direct connections recorded.</div>
                  )}
                </div>
              </div>
            ) : (
              <div className="py-12 text-center text-slate-400 space-y-2">
                <Building2 className="w-8 h-8 mx-auto text-slate-300" />
                <p className="text-[11px]">Click on any node in the graph diagram to inspect its related-party connections and SEC footnote disclosures.</p>
              </div>
            )}
          </div>

          {/* Quick stats footer */}
          <div className="pt-3 border-t border-slate-100 text-[10px] text-slate-500 space-y-1">
            <div className="flex justify-between">
              <span>Total Entities:</span>
              <span className="font-semibold text-slate-800">{nodes.length}</span>
            </div>
            <div className="flex justify-between">
              <span>Reported Transactions:</span>
              <span className="font-semibold text-slate-800">{edges.length}</span>
            </div>
            <div className="flex justify-between">
              <span>Shell / LLC Candidates:</span>
              <span className="font-semibold text-rose-600">{shellCount}</span>
            </div>
          </div>
        </div>
      </div>

      {/* 4. Disclosure Transaction Evidence Cards */}
      <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm space-y-3">
        <div className="flex justify-between items-center">
          <div>
            <h4 className="text-xs font-semibold text-slate-800">
              SEC 10-K Footnote Evidence Sentences ({relevantEvidence.length > 0 ? relevantEvidence.length : edges.length})
            </h4>
            <p className="text-[11px] text-slate-500">
              Verbatim footnote disclosures establishing officer relationships, transactions, and ownership links.
            </p>
          </div>
        </div>

        {relevantEvidence.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
            {relevantEvidence.map((ev, idx) => (
              <div key={idx} className="p-3 rounded bg-slate-50 border border-slate-200 text-xs space-y-1.5">
                <div className="font-semibold text-slate-800 flex items-center justify-between">
                  <div className="flex items-center space-x-1.5 truncate">
                    <span className="text-slate-900 font-medium">{ev.source}</span>
                    <span className="text-slate-400">↔</span>
                    <span className="text-slate-900 font-medium">{ev.target}</span>
                  </div>
                  <span className="text-[9px] font-mono text-sky-700 bg-sky-50 px-1.5 py-0.5 rounded border border-sky-200">
                    {ev.relation}
                  </span>
                </div>
                <p className="text-slate-600 italic text-[11px] bg-white p-2 rounded border border-slate-100">
                  &quot;{ev.evidence_sentence}&quot;
                </p>
              </div>
            ))}
          </div>
        ) : (
          <div className="overflow-x-auto mt-2">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold uppercase tracking-wider text-[10px]">
                  <th className="py-2 px-3">Entity Source</th>
                  <th className="py-2 px-3">Relationship</th>
                  <th className="py-2 px-3">Entity Target</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {edges.slice(0, 8).map((e, idx) => (
                  <tr key={idx} className="hover:bg-slate-50">
                    <td className="py-2 px-3 font-medium text-slate-800">{e.source}</td>
                    <td className="py-2 px-3 font-mono text-sky-700 text-[10px]">{e.relation}</td>
                    <td className="py-2 px-3 text-slate-600">{e.target}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
