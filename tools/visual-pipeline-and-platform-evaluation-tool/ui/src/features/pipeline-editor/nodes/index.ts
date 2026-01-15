import FileSrcNode, { FileSrcNodeWidth } from "./FileSrcNode.tsx";
import QtdemuxNode from "./QtdemuxNode.tsx";
import H264ParseNode from "./H264ParseNode.tsx";
import VAH264DecNode from "./VAH264DecNode.tsx";
import GVAFpsCounterNode from "./GVAFpsCounterNode.tsx";
import GVADetectNode, { GVADetectNodeWidth } from "./GVADetectNode.tsx";
import Queue2Node from "./Queue2Node.tsx";
import GVATrackNode from "./GVATrackNode.tsx";
import GVAWatermarkNode from "./GVAWatermarkNode.tsx";
import GVAMetaConvertNode, {
  GVAMetaConvertNodeWidth,
} from "./GVAMetaConvertNode.tsx";
import GVAMetaPublishNode, {
  GVAMetaPublishNodeWidth,
} from "./GVAMetaPublishNode.tsx";
import FakeSinkNode from "./FakeSinkNode.tsx";
import VideoXRawNode from "./VideoXRawNode.tsx";
import VAPostProcNode from "./VAPostProcNode.tsx";
import VideoXRawWithDimensionsNode from "./VideoXRawWithDimensionsNode.tsx";
import Mp4MuxNode from "./Mp4MuxNode.tsx";
import FileSinkNode from "./FileSinkNode.tsx";
import VAH264EncNode from "./VAH264EncNode.tsx";
import Decodebin3Node from "./Decodebin3Node.tsx";
import QueueNode, { QueueNodeWidth } from "./QueueNode.tsx";
import GVAClassifyNode from "./GVAClassifyNode.tsx";
import VaapiDecodebinNode from "./VaapiDecodebinNode.tsx";
import TeeNode, { TeeNodeWidth } from "./TeeNode.tsx";
import SplitmuxsinkNode, {
  SplitmuxsinkNodeWidth,
} from "./SplitmuxsinkNode.tsx";
import VideoScaleNode from "./VideoScaleNode.tsx";

export const nodeTypes = {
  filesrc: FileSrcNode,
  qtdemux: QtdemuxNode,
  h264parse: H264ParseNode,
  vah264dec: VAH264DecNode,
  gvafpscounter: GVAFpsCounterNode,
  gvadetect: GVADetectNode,
  queue2: Queue2Node,
  gvatrack: GVATrackNode,
  gvawatermark: GVAWatermarkNode,
  gvametaconvert: GVAMetaConvertNode,
  gvametapublish: GVAMetaPublishNode,
  fakesink: FakeSinkNode,
  "video/x-raw(memory:VAMemory)": VideoXRawNode,
  vapostproc: VAPostProcNode,
  "video/x-raw": VideoXRawWithDimensionsNode,
  mp4mux: Mp4MuxNode,
  filesink: FileSinkNode,
  vah264enc: VAH264EncNode,
  decodebin3: Decodebin3Node,
  queue: QueueNode,
  gvaclassify: GVAClassifyNode,
  vaapidecodebin: VaapiDecodebinNode,
  tee: TeeNode,
  splitmuxsink: SplitmuxsinkNode,
  videoscale: VideoScaleNode,
};

export const nodeWidths: Record<string, number> = {
  filesrc: FileSrcNodeWidth,
  gvadetect: GVADetectNodeWidth,
  gvametaconvert: GVAMetaConvertNodeWidth,
  gvametapublish: GVAMetaPublishNodeWidth,
  queue: QueueNodeWidth,
  tee: TeeNodeWidth,
  splitmuxsink: SplitmuxsinkNodeWidth,
};

export const defaultNodeWidth = 220;

export default nodeTypes;
