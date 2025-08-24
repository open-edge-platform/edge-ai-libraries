#!/usr/bin/env python3
"""
Generate comprehensive SceneScape database with detailed region mappings
for Scene Intelligence microservice with 4 flat intersections (no hierarchy) and 16 cameras.
Each scene has proper camera calibration replicated from the reference smart-intersection data.
"""

import json
import uuid
from typing import Dict, List, Any
from datetime import datetime

def load_reference_data(reference_file: str) -> Dict[str, Any]:
    """Load reference data including camera calibrations and region data."""
    with open(reference_file, 'r') as f:
        reference_data = json.load(f)
    
    # Extract region-related data and camera calibrations
    data = {
        'boundingboxes': [],
        'boundingboxpoints': [],
        'regions': [],
        'regionpoints': [],
        'regionoccupancythresholds': [],
        'cameras': []
    }
    
    for item in reference_data:
        model = item.get('model', '')
        if 'boundingbox' in model:
            if model == 'manager.boundingbox':
                data['boundingboxes'].append(item)
            elif model == 'manager.boundingboxpoints':
                data['boundingboxpoints'].append(item)
        elif model == 'manager.region':
            data['regions'].append(item)
        elif model == 'manager.regionpoint':
            data['regionpoints'].append(item)
        elif model == 'manager.regionoccupancythreshold':
            data['regionoccupancythresholds'].append(item)
        elif model == 'manager.cam':
            data['cameras'].append(item)
    
    return data

def generate_comprehensive_database():
    """Generate comprehensive database with 4 flat scenes (no hierarchy)."""
    
    # Load reference data including camera calibrations
    reference_file = "/home/sdp/workbench/edge-ai-suites/metro-ai-suite/metro-vision-ai-app-recipe/smart-intersection/src/webserver/smart-intersection-ri/data.json"
    reference_data = load_reference_data(reference_file)
    
    print(f"Loaded reference data:")
    print(f"  Bounding boxes: {len(reference_data['boundingboxes'])}")
    print(f"  Bounding box points: {len(reference_data['boundingboxpoints'])}")
    print(f"  Regions: {len(reference_data['regions'])}")
    print(f"  Region points: {len(reference_data['regionpoints'])}")
    print(f"  Region occupancy thresholds: {len(reference_data['regionoccupancythresholds'])}")
    print(f"  Camera calibrations: {len(reference_data['cameras'])}")
    
    database = []
    
    # Scene configurations - flat structure, no hierarchy
    scenes = [
        {
            "id": "cb1cf1a0-b936-4d47-9221-3fd5cf24857d", 
            "name": "Intersection-1",
            "dataset_dir": "/home/scenescape/SceneScape/datasets/Intersection-1"
        },
        {
            "id": "8f2a4c5e-d9b1-4e3f-a2c8-1b5d7e9f3a6c",
            "name": "Intersection-2", 
            "dataset_dir": "/home/scenescape/SceneScape/datasets/Intersection-2"
        },
        {
            "id": "3d7b9e1f-c4a6-4f8e-b2d5-6a8c0e2f4b7d",
            "name": "Intersection-3",
            "dataset_dir": "/home/scenescape/SceneScape/datasets/Intersection-3"
        },
        {
            "id": "9a4e6c2d-f1b8-4a3e-c7d9-5e8a1c4f6b9e",
            "name": "Intersection-4",
            "dataset_dir": "/home/scenescape/SceneScape/datasets/Intersection-4"
        }
    ]
    
    # Global intersection data
    intersections = [
        {"id": "intersection-1", "name": "Main St & 1st Ave", "lat": 37.59381, "lon": -122.30188},
        {"id": "intersection-2", "name": "Main St & 2nd Ave", "lat": 37.65000, "lon": -122.32000},  
        {"id": "intersection-3", "name": "2nd St & 1st Ave", "lat": 37.75000, "lon": -122.34000},
        {"id": "intersection-4", "name": "2nd St & 2nd Ave", "lat": 37.86719, "lon": -122.36722}
    ]
    
    # Generate scenes
    for scene in scenes:
        scene_entry = {
            "model": "manager.scene",
            "pk": scene["id"],
            "fields": {
                "name": scene["name"],
                "thumbnail": "",
                "map": "Map_w_daisy_mountain_dr_and_gavilan-ge.jpg",
                "scale": 5.765182197,
                "rotation_x": 0.0,
                "rotation_y": 0.0,
                "rotation_z": 0.0,
                "translation_x": 0.0,
                "translation_y": 0.0,
                "translation_z": 0.0,
                "scale_x": 1.0,
                "scale_y": 1.0,
                "scale_z": 1.0,
                "map_processed": None,
                "output_lla": False,
                "map_corners_lla": None,
                "camera_calibration": "Manual",
                "polycam_data": "",
                "dataset_dir": scene["dataset_dir"],
                "output_dir": f"{scene['dataset_dir']}/output_dir",
                "output": None,
                "retrieval_conf": None,
                "global_descriptor_file": "",
                "number_of_localizations": 50,
                "global_feature": "netvlad",
                "local_feature": {"sift": {}},
                "matcher": {"NN-ratio": {}},
                "minimum_number_of_matches": 20,
                "polycam_hash": "",
                "apriltag_size": 0.162,
                "regulated_rate": 30.0,
                "external_update_rate": 30.0,
                "inlier_threshold": 0.5
            }
        }
        database.append(scene_entry)
    
    # Current PK counters
    sensor_pk = 1
    cam_pk = 1
    
    # Generate sensors and cameras for each scene using reference calibrations
    for i, scene in enumerate(scenes):
        intersection = intersections[i]
        
        # Create 4 cameras per intersection using reference calibrations
        for cam_num in range(1, 5):
            camera_id = f"{intersection['id']}-cam{cam_num}"
            
            # Create sensor
            sensor_entry = {
                "model": "manager.sensor",
                "pk": sensor_pk,
                "fields": {
                    "sensor_id": camera_id,
                    "name": f"{intersection['name']} - Camera {cam_num}",
                    "type": "camera",
                    "scene": scene["id"],
                    "icon": ""
                }
            }
            database.append(sensor_entry)
            
            # Get reference camera calibration (cycle through the 4 reference cameras)
            ref_cam_idx = (cam_num - 1) % len(reference_data['cameras'])
            ref_camera = reference_data['cameras'][ref_cam_idx]
            
            # Create camera with reference calibration
            cam_entry = {
                "model": "manager.cam",
                "pk": cam_pk,
                "fields": {
                    "command": None,
                    "camerachain": None,
                    "threshold": None,
                    "aspect": None,
                    "cv_subsystem": None,
                    "transforms": ref_camera['fields']['transforms'],
                    "transform_type": ref_camera['fields']['transform_type'],
                    "width": ref_camera['fields']['width'],
                    "height": ref_camera['fields']['height'],
                    "scene_x": None,
                    "scene_y": None,
                    "scene_z": None,
                    "intrinsics_fx": ref_camera['fields']['intrinsics_fx'],
                    "intrinsics_fy": ref_camera['fields']['intrinsics_fy'],
                    "intrinsics_cx": ref_camera['fields']['intrinsics_cx'],
                    "intrinsics_cy": ref_camera['fields']['intrinsics_cy'],
                    "distortion_k1": ref_camera['fields']['distortion_k1'],
                    "distortion_k2": ref_camera['fields']['distortion_k2'],
                    "distortion_p1": ref_camera['fields']['distortion_p1'],
                    "distortion_p2": ref_camera['fields']['distortion_p2'],
                    "distortion_k3": ref_camera['fields']['distortion_k3'],
                    "sensor": None,
                    "sensorchain": None,
                    "sensorattrib": None,
                    "window": False,
                    "usetimestamps": False,
                    "virtual": None,
                    "debug": False,
                    "override_saved_intrinstics": False,
                    "frames": None,
                    "stats": False,
                    "waitforstable": False,
                    "preprocess": False,
                    "realtime": False,
                    "faketime": False,
                    "modelconfig": None,
                    "rootcert": None,
                    "cert": None,
                    "cvcores": None,
                    "ovcores": None,
                    "unwarp": False,
                    "ovmshost": None,
                    "framerate": None,
                    "maxcache": None,
                    "filter": "none",
                    "disable_rotation": False,
                    "maxdistance": None
                }
            }
            database.append(cam_entry)
            
            sensor_pk += 1
            cam_pk += 1
    
    # Add bounding boxes and regions for each scene that has cameras
    # Note: In Django, regions inherit from BoundingBox, so they share the same PK
    base_bbox_pk = 1000
    bbox_region_pk_mapping = {}  # Map (scene_idx, old_pk) to new_pk
    
    for scene_idx, scene in enumerate(scenes):
        for bbox in reference_data['boundingboxes']:
            old_pk = bbox['pk']
            new_pk = base_bbox_pk
            bbox_region_pk_mapping[(scene_idx, old_pk)] = new_pk
            
            # Create bounding box
            bbox_entry = {
                "model": "manager.boundingbox",
                "pk": new_pk,
                "fields": bbox['fields'].copy()
            }
            database.append(bbox_entry)
            
            # Create corresponding region with same PK
            region = None
            for r in reference_data['regions']:
                if r['pk'] == old_pk:
                    region = r
                    break
            
            if region:
                region_entry = {
                    "model": "manager.region",
                    "pk": new_pk,  # Same PK as bounding box
                    "fields": {
                        "uuid": str(uuid.uuid4()),
                        "scene": scene["id"],
                        "buffer_size": region['fields']['buffer_size'],
                        "height": region['fields']['height'],
                        "volumetric": region['fields']['volumetric']
                    }
                }
                database.append(region_entry)
            
            base_bbox_pk += 1
    
    # Add bounding box points for each scene
    base_bbox_point_pk = 10000
    bbox_point_pk_mapping = {}  # Map (scene_idx, old_pk) to new_pk
    
    for scene_idx, scene in enumerate(scenes):
        for bbox_point in reference_data['boundingboxpoints']:
            old_pk = bbox_point['pk']
            new_pk = base_bbox_point_pk
            bbox_point_pk_mapping[(scene_idx, old_pk)] = new_pk
            
            bbox_point_entry = {
                "model": "manager.boundingboxpoints",
                "pk": new_pk,
                "fields": bbox_point['fields'].copy()
            }
            database.append(bbox_point_entry)
            base_bbox_point_pk += 1
    
    # Add region points for each scene
    for scene_idx, scene in enumerate(scenes):
        for region_point in reference_data['regionpoints']:
            old_region_pk = region_point['fields']['region']
            old_bbox_point_pk = region_point['pk']
            
            new_region_pk = bbox_region_pk_mapping.get((scene_idx, old_region_pk))
            new_bbox_point_pk = bbox_point_pk_mapping.get((scene_idx, old_bbox_point_pk))
            
            if new_region_pk and new_bbox_point_pk:
                region_point_entry = {
                    "model": "manager.regionpoint",
                    "pk": new_bbox_point_pk,  # Use same PK as bbox point
                    "fields": {
                        "region": new_region_pk
                    }
                }
                database.append(region_point_entry)
    
    # Add region occupancy thresholds for each scene
    base_threshold_pk = 40000
    
    for scene_idx, scene in enumerate(scenes):
        for threshold in reference_data['regionoccupancythresholds']:
            old_region_pk = threshold['fields']['region']
            new_region_pk = bbox_region_pk_mapping.get((scene_idx, old_region_pk))
            
            if new_region_pk:
                threshold_entry = {
                    "model": "manager.regionoccupancythreshold",
                    "pk": base_threshold_pk,
                    "fields": {
                        "region": new_region_pk,
                        "sectors": threshold['fields']['sectors'].copy(),
                        "range_max": threshold['fields']['range_max']
                    }
                }
                database.append(threshold_entry)
                base_threshold_pk += 1
    
    # Add missing asset3d entries and database status (copy from reference)
    with open(reference_file, 'r') as f:
        reference_full_data = json.load(f)
    
    for item in reference_full_data:
        if item.get('model') == 'manager.asset3d':
            # Add asset3d (global, no scene reference)
            asset_entry = {
                "model": "manager.asset3d",
                "pk": item['pk'],
                "fields": item['fields'].copy()
            }
            database.append(asset_entry)
        elif item.get('model') == 'manager.databasestatus':
            # Add database status
            database.append(item)
    
    print(f"\nGenerated comprehensive database:")
    print(f"  Total entries: {len(database)}")
    print(f"  Scenes: {len(scenes)}")
    print(f"  Sensors: {sensor_pk - 1}")
    print(f"  Cameras: {cam_pk - 1}")
    print(f"  Bounding boxes: {len(reference_data['boundingboxes']) * len(scenes)}")
    print(f"  Bounding box points: {len(reference_data['boundingboxpoints']) * len(scenes)}")
    print(f"  Regions: {len(reference_data['regions']) * len(scenes)}")
    print(f"  Region points: {len(reference_data['regionpoints']) * len(scenes)}")
    print(f"  Region thresholds: {len(reference_data['regionoccupancythresholds']) * len(scenes)}")
    
    return database

def main():
    """Main function to generate and save the database."""
    print("Generating comprehensive SceneScape database with detailed regions...")
    
    database = generate_comprehensive_database()
    
    # Save to file
    output_file = "/home/sdp/workbench/edge-ai-libraries/microservices/scene-intelligence/src/webserver/data.json"
    
    with open(output_file, 'w') as f:
        json.dump(database, f, indent=2)
    
    print(f"\nDatabase saved to: {output_file}")
    print("✅ Comprehensive database with regions generated successfully!")

if __name__ == "__main__":
    main()
