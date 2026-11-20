# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import struct
import base64

## Policies to post process data

def _isDetection(item):
  """Check if item contains valid detection metadata."""
  detection = item.get('detection')
  return isinstance(detection, dict) and 'confidence' in detection

def _isReidTensor(tensor):
  """Check if a tensor holds a raw re-id embedding vector."""
  name = tensor.get('name', '') or tensor.get('tensor_name', '')
  if 'reid' in name or 'embedding' in name:
    return True
  if name == 'detection':
    return False
  return bool(tensor.get('data')) and 'label' not in tensor and 'label_id' not in tensor

def _isClassificationTensor(tensor):
  """Check if a tensor holds semantic classification metadata."""
  name = tensor.get('name', '') or tensor.get('tensor_name', '')
  return bool(name and name != 'detection' and 'label' in tensor and not _isReidTensor(tensor))

def _extractKeypointsFromGvametaconvert(item):
  """Extract keypoints from gvametaconvert format (yolo11-pose and similar)."""
  raw_keypoints = item.get('keypoints')
  if isinstance(raw_keypoints, list):
    for kp_group in raw_keypoints:
      points = kp_group.get('points', [])
      if points:
        keypoints = [
          {
            'name': p['name'],
            'x': p['x'],
            'y': p['y'],
            'confidence': p.get('confidence'),
          }
          for p in points
          if 'name' in p and 'x' in p and 'y' in p
        ]
        skeleton = kp_group.get('skeleton', [])
        point_names = [p.get('name', '') for p in points]
        connections = []
        for pair in skeleton:
          if (isinstance(pair, (list, tuple)) and len(pair) == 2
              and pair[0] < len(point_names) and pair[1] < len(point_names)):
            connections.append(point_names[pair[0]])
            connections.append(point_names[pair[1]])
        return {
          'keypoints': keypoints,
          'keypoint_connections': connections,
        }
  return {}

def _extractKeypoints(item):
  # Format 1: keypoints in tensors (older model-proc based pipelines)
  for tensor in item.get('tensors', []):
    if tensor.get('format') == 'keypoints':
      data = tensor.get('data', [])
      names = tensor.get('point_names', [])
      keypoints = [
        {'name': names[i], 'x': data[i * 2], 'y': data[i * 2 + 1]}
        for i in range(len(names))
        if i * 2 + 1 < len(data)
      ]
      return {
        'keypoints': keypoints,
        'keypoint_connections': tensor.get('point_connections', [])
      }

  # Format 2: keypoints from gvametaconvert (yolo11-pose and similar)
  return _extractKeypointsFromGvametaconvert(item)

def detectionPolicy(pobj, item, fw, fh):
  if not _isDetection(item):
    return
  detection = item['detection']
  # If label is missing use label_id to avoid KeyError exception.
  category = detection.get('label') or str(detection['label_id'])
  pobj.update({
    'category': category,
    'confidence': detection['confidence']
  })
  pobj.update({
    'bounding_box_px': {'x': item['x'], 'y': item['y'], 'width': item['w'], 'height': item['h']}
  })
  pobj.update(_extractKeypoints(item))
  return

def detection3DPolicy(pobj, item, fw, fh):
  if not _isDetection(item):
    return
  pobj.update({
    'category': item['detection']['label'],
    'confidence': item['detection']['confidence'],
  })

  computeObjBoundingBoxParams3D(pobj, item)

  if not ('bounding_box_px' in pobj or 'rotation' in pobj):
    print(f"Warning: No bounding box or rotation data found in item {item}")
  return

def reidPolicy(pobj, item, fw, fh):
  if not _isDetection(item):
    return
  classificationPolicy(pobj, item, fw, fh)
  for tensor in item.get('tensors', [{}]):
    if _isReidTensor(tensor):
      reid_vector = tensor.get('data', [])
      # Handle variable-length re-id vectors from different models
      if not reid_vector:
        continue
      vector_len = len(reid_vector)
      # Pack vector with its actual dimensions
      format_string = f"{vector_len}f"
      try:
        v = struct.pack(format_string, *reid_vector)
      except struct.error as e:
        import sys
        print(f"Failed to pack reid vector of length {vector_len}: {e}", file=sys.stderr)
        continue
      # Move reid under metadata key
      if 'metadata' not in pobj:
        pobj['metadata'] = {}
      pobj['metadata']['reid'] = {
        'embedding_vector': base64.b64encode(v).decode('utf-8'),
        'model_name': tensor.get('model_name', tensor.get('semantic_tag', ''))
      }
      break
  return

def classificationPolicy(pobj, item, fw, fh):
  """Extract detection and classification metadata from tensors and update pobj"""
  if not _isDetection(item):
    return
  detectionPolicy(pobj, item, fw, fh)

  # Initialize metadata dict if it doesn't exist
  if 'metadata' not in pobj:
    pobj['metadata'] = {}

  categories = {}
  for tensor in item.get('tensors', [{}]):
    if _isClassificationTensor(tensor):
      metadata_dict = {
        'label': tensor.get('label', ''),
        'model_name': tensor.get('model_name', tensor.get('semantic_tag', ''))
      }
      if 'confidence' in tensor:
        metadata_dict['confidence'] = tensor.get('confidence')
      name = tensor.get('name', '') or tensor.get('tensor_name', '')
      categories[name] = metadata_dict

  # Move all semantic metadata under metadata key
  pobj['metadata'].update(categories)
  return

def ocrPolicy(pobj, item, fw, fh):
  if not _isDetection(item):
    return
  detection3DPolicy(pobj, item, fw, fh)
  pobj['text'] = ''
  for key, value in item.items():
    if key.startswith('classification_layer') and isinstance(value, dict) and 'label' in value:
      pobj['text'] = value['label']
      break
  return

## Utility functions

def computeObjBoundingBoxParams3D(pobj, item):
  if 'extra_params' in item and all(k in item['extra_params'] for k in ['translation', 'rotation', 'dimension']):
    pobj.update({
      'translation': item['extra_params']['translation'],
      'rotation': item['extra_params']['rotation'],
      'size': item['extra_params']['dimension']
    })

    x_min, y_min, z_min = pobj['translation']
    x_size, y_size, z_size = pobj['size']
    x_max, y_max, z_max = x_min + x_size, y_min + y_size, z_min + z_size

    bbox_width = x_max - x_min
    bbox_height = y_max - y_min
    bbox_depth = z_max - z_min

    pobj['bounding_box_3D'] = {
      'x': x_min,
      'y': y_min,
      'z': z_min,
      'width': bbox_width,
      'height': bbox_height,
      'depth': bbox_depth
    }

  return
