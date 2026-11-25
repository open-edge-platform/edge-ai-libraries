# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import cv2
import numpy as np

# Buffer added to vehicle bounds to account for potential inaccuracies in 3D object detection.
VEHICLE_BOUNDS_BUFFER = 0.15
OVERLAP_SCORE_THRESHOLD = 0.1

class Object3DChainedDataProcessor:
  """Utility class for associating 3D primary objects with 2D secondary objects"""

  def __init__(self):
    self.associations_created = 0

  def getCuboidVertices(self, bbox3D, rotation=None):
    """Creates vertices for cuboid based on (x, y, z) and (width, height, depth)"""
    width = bbox3D['width']
    height = bbox3D['height']
    depth = bbox3D['depth']
    x = bbox3D['x']
    y = bbox3D['y']
    z = bbox3D['z']

    vertices = np.zeros([3, 8])

    # Setup X, Y and Z respectively
    vertices[0, [0, 1, 4, 5]], vertices[0, [2, 3, 6, 7]] = width / 2, -width / 2
    vertices[1, [0, 3, 4, 7]], vertices[1, [1, 2, 5, 6]] = height / 2, -height / 2
    vertices[2, [0, 1, 2, 3]], vertices[2, [4, 5, 6, 7]] = 0, depth

    # Rotate if rotation is provided
    if rotation is not None:
      if len(rotation) == 4:  # quaternion
        from scipy.spatial.transform import Rotation
        vertices = Rotation.from_quat(rotation).as_matrix() @ vertices

    # Translate
    vertices[0, :] += x
    vertices[1, :] += y
    vertices[2, :] += z

    vertices = np.transpose(vertices)
    return vertices

  def findClosestFace(self, vertices):
    """Find the closest face of the 3D bounding box (smallest average z)"""
    faces = [
      [0, 1, 2, 3],  # bottom
      [4, 5, 6, 7],  # top
      [0, 1, 5, 4],  # front
      [2, 3, 7, 6],  # back
      [1, 2, 6, 5],  # right
      [0, 3, 7, 4]   # left
    ]

    min_face = 0
    min_z = float('inf')

    for f, face in enumerate(faces):
      z_avg = np.mean([vertices[i][2] for i in face])
      if z_avg < min_z:
        min_z = z_avg
        min_face = f

    return faces[min_face]

  def project3DTo2D(self, vertices, intrinsics):
    """Project 3D vertices to 2D using camera intrinsics"""
    if intrinsics is None:
      return None

    intrinsics = np.array(intrinsics).reshape(3, 3)
    pts_img = intrinsics @ vertices.T

    if np.all(np.absolute(pts_img[2]) > 1e-7):
      pts_img = pts_img[:2] / pts_img[2]
      return pts_img.T.astype(np.int32)
    else:
      return None

  def calculate3DBounds2D(self, car_3d, intrinsics):
    """Calculate 2D projection bounds of a 3D car bounding box"""
    try:
      # Get 3D vertices
      vertices = self.getCuboidVertices(car_3d['bounding_box_3D'], car_3d.get('rotation'))

      projected_vertices = self.project3DTo2D(vertices, intrinsics)
      if projected_vertices is None:
        return None

      x_coords = projected_vertices[:, 0]
      y_coords = projected_vertices[:, 1]

      return {
        'x': int(np.min(x_coords)),
        'y': int(np.min(y_coords)),
        'width': int(np.max(x_coords) - np.min(x_coords)),
        'height': int(np.max(y_coords) - np.min(y_coords))
      }
    except Exception as e:
      print(f"Error calculating 3D bounds: {e}")
      return None

  def calculate3DFaceBounds2D(self, car_3d, intrinsics):
    """Calculate 2D projection of the closest face of a 3D car bounding box"""
    try:
      vertices = self.getCuboidVertices(car_3d['bounding_box_3D'], car_3d.get('rotation'))

      # Find closest face
      closest_face_indices = self.findClosestFace(vertices)
      closest_face_vertices = vertices[closest_face_indices]

      # Project closest face to 2D
      projected_face = self.project3DTo2D(closest_face_vertices, intrinsics)
      if projected_face is None:
        return None

      # Get bounding rectangle of the face
      x_coords = projected_face[:, 0]
      y_coords = projected_face[:, 1]

      return {
        'x': int(np.min(x_coords)),
        'y': int(np.min(y_coords)),
        'width': int(np.max(x_coords) - np.min(x_coords)),
        'height': int(np.max(y_coords) - np.min(y_coords))
      }
    except Exception as e:
      print(f"Error calculating 3D face bounds: {e}")
      return None

  def calculate3DOverlapScore(self, primary_obj_3d, secondary_bbox, intrinsics, use_face_projection=True):
    try:
      if use_face_projection:
        primary_2d_bounds = self.calculate3DFaceBounds2D(primary_obj_3d, intrinsics)
      else:
        primary_2d_bounds = self.calculate3DBounds2D(primary_obj_3d, intrinsics)

      if primary_2d_bounds is None:
        return 0.0

      secondary_x1, secondary_y1 = secondary_bbox['x'], secondary_bbox['y']
      secondary_x2, secondary_y2 = secondary_x1 + secondary_bbox['width'], secondary_y1 + secondary_bbox['height']
      secondary_center_x = (secondary_x1 + secondary_x2) / 2
      secondary_center_y = (secondary_y1 + secondary_y2) / 2

      primary_x1, primary_y1 = primary_2d_bounds['x'], primary_2d_bounds['y']
      primary_x2, primary_y2 = primary_x1 + primary_2d_bounds['width'], primary_y1 + primary_2d_bounds['height']

      primary_width = primary_x2 - primary_x1
      primary_height = primary_y2 - primary_y1
      margin_x = primary_width * VEHICLE_BOUNDS_BUFFER
      margin_y = primary_height * VEHICLE_BOUNDS_BUFFER

      expanded_primary_x1 = primary_x1 - margin_x
      expanded_primary_y1 = primary_y1 - margin_y
      expanded_primary_x2 = primary_x2 + margin_x
      expanded_primary_y2 = primary_y2 + margin_y

      if (expanded_primary_x1 <= secondary_center_x <= expanded_primary_x2 and
        expanded_primary_y1 <= secondary_center_y <= expanded_primary_y2):

        primary_center_x = (primary_x1 + primary_x2) / 2
        primary_center_y = (primary_y1 + primary_y2) / 2
        distance = ((secondary_center_x - primary_center_x) ** 2 + (secondary_center_y - primary_center_y) ** 2) ** 0.5

        primary_diagonal = (primary_width ** 2 + primary_height ** 2) ** 0.5
        if primary_diagonal > 0:
          normalized_distance = distance / primary_diagonal
          return max(0, 1.0 - normalized_distance)

      return 0.0
    except Exception as e:
      print(f"Error calculating 3D overlap score: {e}")
      return 0.0

  def associateObjects(self, objects, primary_type='car', secondary_type='license_plate', intrinsics=None):
    primary_objects = objects.get(primary_type, [])
    secondary_objects = objects.get(secondary_type, [])

    if not primary_objects or not secondary_objects or intrinsics is None:
      return []

    used_secondary = set()
    associations_created = 0
    sub_detections = [secondary_type]

    for primary_idx, primary_obj in enumerate(primary_objects):
      associated_secondary = []

      if 'bounding_box_3D' not in primary_obj and 'translation' in primary_obj:
        primary_obj['bounding_box_3D'] = {
          'x': primary_obj['translation'][0],
          'y': primary_obj['translation'][1],
          'z': primary_obj['translation'][2],
          'width': primary_obj['size'][0],
          'height': primary_obj['size'][1],
          'depth': primary_obj['size'][2]
        }

      secondary_scores = []
      for secondary_idx, secondary_obj in enumerate(secondary_objects):
        if secondary_idx in used_secondary:
          continue

        secondary_bbox = secondary_obj['bounding_box_px']
        score = self.calculate3DOverlapScore(primary_obj, secondary_bbox, intrinsics, use_face_projection=True)
        if score > OVERLAP_SCORE_THRESHOLD:
          secondary_scores.append((score, secondary_idx, secondary_obj))

      secondary_scores.sort(reverse=True, key=lambda x: x[0])

      for score, secondary_idx, secondary_obj in secondary_scores[:2]:
        secondary_info = {
          'bounding_box_px': secondary_obj['bounding_box_px'],
          'confidence': secondary_obj['confidence'],
        }

        if 'text' in secondary_obj:
          secondary_info['text'] = secondary_obj['text']

        associated_secondary.append(secondary_info)
        used_secondary.add(secondary_idx)
        associations_created += 1

      if associated_secondary:
        primary_obj[f'{secondary_type}s'] = associated_secondary

    remaining_secondary = [obj for idx, obj in enumerate(secondary_objects) if idx not in used_secondary]
    if remaining_secondary:
      print(f"Warning: Not all {secondary_type} objects were associated with {primary_type} objects. Remaining: {len(remaining_secondary)}")

    del objects[secondary_type]
    self.associations_created = associations_created
    return sub_detections

  def annotateObjectAssociations(self, img, objects, obj_colors, primary_type='car', secondary_type='license_plate', intrinsics=None, scale=1.0):
    """Draw associations on `img`; `scale` maps native pixel coordinates and intrinsics onto it."""
    primary_objects = objects.get(primary_type, [])

    if not primary_objects or intrinsics is None:
      return

    if scale != 1.0:
      intrinsics = np.array(intrinsics, dtype=float).reshape(3, 3) * [[scale], [scale], [1.0]]

    for obj in primary_objects:
      if 'bounding_box_3D' not in obj and 'translation' in obj:
        obj['bounding_box_3D'] = {
          'x': obj['translation'][0],
          'y': obj['translation'][1],
          'z': obj['translation'][2],
          'width': obj['size'][0],
          'height': obj['size'][1],
          'depth': obj['size'][2]
        }

      self.annotate3DObject(img, obj, intrinsics, color=obj_colors[1])

      secondary_key = f'{secondary_type}s'
      if secondary_key in obj:
        for secondary_obj in obj[secondary_key]:
          bounds = {key: value * scale for key, value in secondary_obj['bounding_box_px'].items()}
          secondary_topleft = (int(bounds['x']), int(bounds['y']))
          secondary_bottomright = (int(bounds['x'] + bounds['width']), int(bounds['y'] + bounds['height']))
          cv2.rectangle(img, secondary_topleft, secondary_bottomright, obj_colors[3], 2)

          if 'text' in secondary_obj and secondary_obj['text']:
            self.annotateText(img, bounds, secondary_obj['text'])

  def annotate3DObject(self, img, obj, intrinsics, color=(66, 186, 150), thickness=2):
    try:
      vertex_idxs = [0, 1, 2, 3, 7, 6, 5, 4, 7, 3, 0, 4, 5, 1, 2, 6]
      rotation = obj.get('rotation')

      vertices = self.getCuboidVertices(obj['bounding_box_3D'], rotation)

      transformed_vertices = self.project3DTo2D(vertices, intrinsics)
      if transformed_vertices is None:
        return

      for idx in range(len(vertex_idxs)-1):
        if (vertex_idxs[idx] < len(transformed_vertices) and
          vertex_idxs[idx+1] < len(transformed_vertices)):
          cv2.line(img,
              tuple(transformed_vertices[vertex_idxs[idx]]),
              tuple(transformed_vertices[vertex_idxs[idx+1]]),
              color=(255,0,0) if idx == 0 else color,
              thickness=thickness)
    except Exception as e:
      print(f"Error annotating 3D object: {e}")

  def annotateText(self, frame, bounds, text):
    scale = 1
    lsize = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1*scale, 5*scale)[0]

    if lsize[0] > 0:
      scale = scale * 2 * bounds['width'] / lsize[0]
    lsize = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1*scale, int(5*scale))[0]

    start_x = int(bounds['x'] - lsize[0])
    bottom_y = int(bounds['y'] + 10 + lsize[1])
    end_x = int(bounds['x'])
    top_y = int(bounds['y'] + 10)

    if self.pointsInsideImage(frame, [[start_x, top_y], [end_x, bottom_y]]):
      cv2.putText(frame, text, (start_x, bottom_y),
            cv2.FONT_HERSHEY_SIMPLEX, 1 * scale, (0,0,0), int(5 * scale))
      cv2.putText(frame, text, (start_x, bottom_y),
            cv2.FONT_HERSHEY_SIMPLEX, 1 * scale, (255,255,255), int(2 * scale))

  def pointsInsideImage(self, frame, img_pts):
    frame_height, frame_width = frame.shape[:2]
    for point in img_pts:
      pt_x = int(point[0])
      pt_y = int(point[1])
      if pt_x < 0 or pt_x > frame_width or pt_y < 0 or pt_y > frame_height:
        return False
    return True
