import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog.tsx";
import { Braces } from "lucide-react";
import type { Edge, Node, Viewport } from "@xyflow/react";

type StatePreviewButtonProps = {
  nodes: Node[];
  edges: Edge[];
  viewport: Viewport;
};

const StatePreviewButton = ({
  nodes,
  edges,
  viewport,
}: StatePreviewButtonProps) => {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <button className="bg-blue-600 hover:bg-blue-700 text-white p-2 rounded-lg shadow-lg transition-colors">
          <Braces className="w-5 h-5" />
        </button>
      </DialogTrigger>
      <DialogContent className="max-w-4xl max-h-[80vh] overflow-hidden">
        <DialogHeader>
          <DialogTitle>Pipeline State</DialogTitle>
          <DialogDescription>
            Current nodes and edges state of the React Flow pipeline
          </DialogDescription>
        </DialogHeader>
        <div className="overflow-auto max-h-[60vh]">
          <div className="space-y-4">
            <div>
              <h3 className="text-lg font-semibold mb-2">
                Nodes ({nodes.length})
              </h3>
              <pre className="bg-gray-100 p-4 rounded-lg text-sm overflow-auto">
                {JSON.stringify(nodes, null, 2)}
              </pre>
            </div>
            <div>
              <h3 className="text-lg font-semibold mb-2">
                Edges ({edges.length})
              </h3>
              <pre className="bg-gray-100 p-4 rounded-lg text-sm overflow-auto">
                {JSON.stringify(edges, null, 2)}
              </pre>
            </div>
            <div>
              <h3 className="text-lg font-semibold mb-2">Viewport</h3>
              <pre className="bg-gray-100 p-4 rounded-lg text-sm overflow-auto">
                {JSON.stringify(viewport, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default StatePreviewButton;
