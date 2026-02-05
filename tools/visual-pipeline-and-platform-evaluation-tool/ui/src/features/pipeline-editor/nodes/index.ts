import Decodebin3Node from "./Decodebin3Node.tsx";
import FakeSinkNode from "./FakeSinkNode.tsx";
import FileSinkNode from "./FileSinkNode.tsx";
import FileSrcNode from "./FileSrcNode.tsx";
import GVAClassifyNode, { GVAClassifyNodeWidth } from "./GVAClassifyNode.tsx";
import GVADetectNode, { GVADetectNodeWidth } from "./GVADetectNode.tsx";
import GVAFpsCounterNode, {
  GVAFpsCounterNodeWidth,
} from "./GVAFpsCounterNode.tsx";
import GVAMetaConvertNode, {
  GVAMetaConvertNodeWidth,
} from "./GVAMetaConvertNode.tsx";
import GVAMetaPublishNode, {
  GVAMetaPublishNodeWidth,
} from "./GVAMetaPublishNode.tsx";
import GVATrackNode from "./GVATrackNode.tsx";
import GVAWatermarkNode, {
  GVAWatermarkNodeWidth,
} from "./GVAWatermarkNode.tsx";
import H264ParseNode from "./H264ParseNode.tsx";
import Mp4MuxNode from "./Mp4MuxNode.tsx";
import QtdemuxNode from "./QtdemuxNode.tsx";
import Queue2Node from "./Queue2Node.tsx";
import QueueNode from "./QueueNode.tsx";
import SplitmuxsinkNode from "./SplitmuxsinkNode.tsx";
import TeeNode from "./TeeNode.tsx";
import VaapiDecodebinNode from "./VaapiDecodebinNode.tsx";
import VAH264DecNode from "./VAH264DecNode.tsx";
import VAH264EncNode from "./VAH264EncNode.tsx";
import VAPostProcNode from "./VAPostProcNode.tsx";
import VideoConvertNode, {
  VideoConvertNodeWidth,
} from "./VideoConvertNode.tsx";
import VideoScaleNode from "./VideoScaleNode.tsx";
import VideoXRawNode from "./VideoXRawNode.tsx";
import VideoXRawWithDimensionsNode from "./VideoXRawWithDimensionsNode.tsx";
import AvDecH264Node from "./AvDecH264Node.tsx";

export const nodeTypes = {
  filesrc: FileSrcNode,
  qtdemux: QtdemuxNode,
  h264parse: H264ParseNode,
  vah264dec: VAH264DecNode,
  avdec_h264: AvDecH264Node,
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
  videoconvert: VideoConvertNode,
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
  gvadetect: GVADetectNodeWidth,
  gvaclassify: GVAClassifyNodeWidth,
  gvametaconvert: GVAMetaConvertNodeWidth,
  gvametapublish: GVAMetaPublishNodeWidth,
  gvafpscounter: GVAFpsCounterNodeWidth,
  gvawatermark: GVAWatermarkNodeWidth,
  videoconvert: VideoConvertNodeWidth,
};

export const nodeHeights: Record<string, number> = {
  filesrc: 100,
  gvadetect: 180,
  gvaclassify: 180,
  gvatrack: 130,
  "video/x-raw(memory:VAMemory)": 150,
};

export const defaultNodeWidth = 220;
export const defaultNodeHeight = 60;

export default nodeTypes;
