import { useState, useRef, useCallback, useEffect } from "react";
import type {
  Node as ReactFlowNode,
  Edge as ReactFlowEdge,
} from "@xyflow/react";

interface UseUndoRedoOptions {
  debounceMs?: number;
  maxHistorySize?: number;
}

const normalizeNodesForHistory = (nodes: ReactFlowNode[]) =>
  // The history of graph edits track only position and data changes
  // Excluded: selected, dragging, width, height, etc.
  nodes.map((node) => ({
    id: node.id,
    type: node.type,
    position: node.position,
    data: node.data,
  }));

export const useUndoRedo = (options: UseUndoRedoOptions = {}) => {
  const { debounceMs = 500, maxHistorySize = 50 } = options;

  const [currentNodes, setCurrentNodes] = useState<ReactFlowNode[]>([]);
  const [currentEdges, setCurrentEdges] = useState<ReactFlowEdge[]>([]);
  const [history, setHistory] = useState<
    Array<{ nodes: ReactFlowNode[]; edges: ReactFlowEdge[] }>
  >([]);
  const [historyIndex, setHistoryIndex] = useState(-1);

  const isUndoRedoAction = useRef(false);
  const historyTimerRef = useRef<number | null>(null);
  const lastHistoryStateRef = useRef<{
    nodes: ReactFlowNode[];
    edges: ReactFlowEdge[];
  } | null>(null);

  const handleNodesChange = useCallback((nodes: ReactFlowNode[]) => {
    setCurrentNodes(nodes);
  }, []);

  const handleEdgesChange = useCallback((edges: ReactFlowEdge[]) => {
    setCurrentEdges(edges);
  }, []);

  const addToHistory = useCallback(
    (nodes: ReactFlowNode[], edges: ReactFlowEdge[]) => {
      if (isUndoRedoAction.current) return;

      const normalizedNodes = normalizeNodesForHistory(nodes);

      if (lastHistoryStateRef.current) {
        const normalizedLastNodes = normalizeNodesForHistory(
          lastHistoryStateRef.current.nodes,
        );
        const nodesChanged =
          JSON.stringify(normalizedNodes) !==
          JSON.stringify(normalizedLastNodes);
        const edgesChanged =
          JSON.stringify(edges) !==
          JSON.stringify(lastHistoryStateRef.current.edges);
        if (!nodesChanged && !edgesChanged) return;
      }

      lastHistoryStateRef.current = { nodes, edges };

      setHistory((prev) => {
        const newHistory = prev.slice(0, historyIndex + 1);
        const stateCopy = {
          nodes: JSON.parse(JSON.stringify(nodes)),
          edges: JSON.parse(JSON.stringify(edges)),
        };
        newHistory.push(stateCopy);
        if (newHistory.length > maxHistorySize) {
          newHistory.shift();
          return newHistory;
        }
        return newHistory;
      });
      setHistoryIndex((prev) => Math.min(prev + 1, maxHistorySize - 1));
    },
    [historyIndex, maxHistorySize],
  );

  const undo = useCallback(() => {
    if (historyIndex > 0) {
      isUndoRedoAction.current = true;
      const prevState = history[historyIndex - 1];
      setCurrentNodes(prevState.nodes);
      setCurrentEdges(prevState.edges);
      setHistoryIndex(historyIndex - 1);
      setTimeout(() => {
        isUndoRedoAction.current = false;
      }, 0);
    }
  }, [historyIndex, history]);

  const redo = useCallback(() => {
    if (historyIndex < history.length - 1) {
      isUndoRedoAction.current = true;
      const nextState = history[historyIndex + 1];
      setCurrentNodes(nextState.nodes);
      setCurrentEdges(nextState.edges);
      setHistoryIndex(historyIndex + 1);
      setTimeout(() => {
        isUndoRedoAction.current = false;
      }, 0);
    }
  }, [historyIndex, history]);

  const resetHistory = useCallback(() => {
    setHistory([]);
    setHistoryIndex(-1);
    lastHistoryStateRef.current = null;
    if (historyTimerRef.current) {
      clearTimeout(historyTimerRef.current);
      historyTimerRef.current = null;
    }
  }, []);

  const setInitialState = useCallback(
    (nodes: ReactFlowNode[], edges: ReactFlowEdge[]) => {
      setCurrentNodes(nodes);
      setCurrentEdges(edges);
      if (nodes.length > 0 || edges.length > 0) {
        setHistory([
          {
            nodes: JSON.parse(JSON.stringify(nodes)),
            edges: JSON.parse(JSON.stringify(edges)),
          },
        ]);
        setHistoryIndex(0);
        lastHistoryStateRef.current = { nodes, edges };
      }
    },
    [],
  );

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (
        (event.ctrlKey || event.metaKey) &&
        event.key === "z" &&
        !event.shiftKey
      ) {
        event.preventDefault();
        undo();
      } else if (
        (event.ctrlKey || event.metaKey) &&
        (event.key === "y" || (event.key === "z" && event.shiftKey))
      ) {
        event.preventDefault();
        redo();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [undo, redo]);

  useEffect(() => {
    if (isUndoRedoAction.current) return;

    if (historyTimerRef.current) {
      clearTimeout(historyTimerRef.current);
    }

    historyTimerRef.current = setTimeout(() => {
      if (currentNodes.length > 0 || currentEdges.length > 0) {
        addToHistory(currentNodes, currentEdges);
      }
    }, debounceMs);

    return () => {
      if (historyTimerRef.current) {
        clearTimeout(historyTimerRef.current);
      }
    };
  }, [currentNodes, currentEdges, addToHistory, debounceMs]);

  return {
    currentNodes,
    currentEdges,
    canUndo: historyIndex > 0,
    canRedo: historyIndex < history.length - 1,
    handleNodesChange,
    handleEdgesChange,
    setCurrentNodes,
    setCurrentEdges,
    undo,
    redo,
    resetHistory,
    setInitialState,
  };
};
