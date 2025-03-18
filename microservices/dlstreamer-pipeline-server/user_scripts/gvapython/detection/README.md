### Add Detection ROIs:

This python script adds ROIs to video frame.

It is expected to be used after `udfloader` element in a object detection pipeline and along with `gvatrack` for object tracking for UDFs. Standalone usage of this script is NOT recommended. For more details on the usage, refer to this [doc](../../../eii/docs/object_tracking.md)

Specific metadata format is expected out of UDF for regions to be added to video frame which has to be DCaaS compatible and the bounding box coordinates in the form x1, y1, x2, y2 (top, left, bottom, right). Refer to [Geti UDF](../../udfs/python/geti_udf/geti_udf.py) for more details on the format. 
