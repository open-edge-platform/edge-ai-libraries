"""Directional traffic density service for calculating traffic flow by direction."""

import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class DirectionalTrafficData:
    """Directional traffic data for an intersection."""
    intersection_id: str
    intersection_name: str
    latitude: float
    longitude: float
    timestamp: datetime
    northbound_density: int
    southbound_density: int
    eastbound_density: int
    westbound_density: int
    total_density: int
    region_counts: Dict[str, Dict[str, int]]  # region_uuid -> {vehicle: count, pedestrian: count}


@dataclass
class IntersectionDirectionalSummary:
    """Summary of directional traffic for all intersections."""
    timestamp: datetime
    total_intersections: int
    intersections: List[DirectionalTrafficData]
    overall_northbound: int
    overall_southbound: int
    overall_eastbound: int
    overall_westbound: int
    overall_total: int


class DirectionalTrafficService:
    """Service for calculating directional traffic density."""
    
    # Traffic density formulas using region names instead of numbers
    TRAFFIC_FORMULAS = {
        'northbound': ['NBLANE', 'WBNBRTLANE', 'EBNBLTLANE'],               # North bound lanes and turns
        'southbound': ['SBLANE', 'WBSBLTLANE', 'EBSBRTLANE'],               # South bound lanes and turns  
        'eastbound': ['EBLANE', 'NBEBRTLANE', 'SBEBLTLANE'],                # East bound lanes and turns
        'westbound': ['WBLANE', 'NBWBLTLANE']                               # West bound lanes and turns
    }
    
    # Intersection coordinates (lat, lng) - coordinates in San Francisco Bay Area
    INTERSECTION_COORDINATES = {
        'cb1cf1a0-b936-4d47-9221-3fd5cf24857d': {'latitude': 37.86719, 'longitude': -122.30188, 'name': 'Main St & 1st Ave'},
        '8f2a4c5e-d9b1-4e3f-a2c8-1b5d7e9f3a6c': {'latitude': 37.59381, 'longitude': -122.36722, 'name': 'Main St & 2nd Ave'},
        '3d7b9e1f-c4a6-4f8e-b2d5-6a8c0e2f4b7d': {'latitude': 37.73789, 'longitude': -122.40806, 'name': '2nd St & 1st Ave'},
        '9a4e6c2d-f1b8-4a3e-c7d9-5e8a1c4f6b9e': {'latitude': 37.49076, 'longitude': -122.21788, 'name': '2nd St & 2nd Ave'}
    }
    
    def __init__(self, config_service):
        """Initialize directional traffic service."""
        self.config = config_service
        self.region_mapping = {}  # scene_id -> {region_name -> region_uuid}
        self.region_counts = {}   # region_uuid -> {vehicle: count, pedestrian: count}
        self._load_region_mapping()
        logger.info("Directional traffic service initialized")
    
    def _load_region_mapping(self):
        """Load region number to UUID mapping from database."""
        try:
            import os
            
            # Try multiple locations for the data file
            data_paths = [
                "/app/data/data.json",  # Docker container path
                # Relative to current service file: services/ -> scene_intelligence/ -> src/ -> webserver/
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "webserver", "data.json")
            ]
            
            data = None
            data_file = None
            
            for path in data_paths:
                try:
                    with open(path, 'r') as f:
                        data = json.load(f)
                        data_file = path
                        break
                except (FileNotFoundError, json.JSONDecodeError) as e:
                    logger.debug(f"Failed to load data from {path}: {str(e)}")
                    continue
            
            if data is None:
                raise FileNotFoundError(f"Could not find data.json in any of these locations: {data_paths}")
            
            # Validate data structure
            if not isinstance(data, list):
                raise ValueError("data.json must contain a list of objects")
            
            # Extract regions and bounding boxes
            regions = [item for item in data if item.get('model') == 'manager.region']
            boundingboxes = [item for item in data if item.get('model') == 'manager.boundingbox']
            
            if not regions:
                raise ValueError("No regions found in data.json - missing manager.region entries")
            
            if not boundingboxes:
                raise ValueError("No bounding boxes found in data.json - missing manager.boundingbox entries")
            
            # Create mapping of PK to region names
            bbox_names = {}
            for bb in boundingboxes:
                if 'pk' not in bb or 'fields' not in bb or 'name' not in bb['fields']:
                    logger.warning(f"Invalid bounding box entry: missing required fields", entry=bb)
                    continue
                bbox_names[bb['pk']] = bb['fields']['name']
            
            # Build scene -> region mappings
            scenes = {}
            missing_fields_count = 0
            
            for region in regions:
                # Validate required fields
                if 'fields' not in region:
                    logger.warning("Region missing 'fields'", region=region)
                    missing_fields_count += 1
                    continue
                
                fields = region['fields']
                required_fields = ['scene', 'uuid']
                missing = [field for field in required_fields if field not in fields]
                
                if missing:
                    logger.warning(f"Region missing required fields: {missing}", region=region)
                    missing_fields_count += 1
                    continue
                
                scene_id = fields['scene']
                region_pk = region.get('pk')
                region_uuid = fields['uuid']
                region_name = bbox_names.get(region_pk, f'Region-{region_pk}' if region_pk else 'Unknown')
                
                if not scene_id or not region_uuid:
                    logger.warning("Region has empty scene_id or uuid", region=region)
                    missing_fields_count += 1
                    continue
                
                if scene_id not in scenes:
                    scenes[scene_id] = []
                scenes[scene_id].append((region_pk, region_uuid, region_name))
            
            if missing_fields_count > 0:
                logger.warning(f"Skipped {missing_fields_count} regions due to missing required fields")
            
            if not scenes:
                raise ValueError("No valid scenes found in data.json after validation")
            
            # Create name-based mappings for each scene
            for scene_id, region_list in scenes.items():
                self.region_mapping[scene_id] = {}
                for pk, uuid, name in region_list:
                    self.region_mapping[scene_id][name] = {
                        'uuid': uuid,
                        'pk': pk
                    }
            
            # Validate we have the expected regions per scene
            for scene_id, regions in self.region_mapping.items():
                if len(regions) < 10:  # Each intersection should have multiple regions
                    logger.warning(f"Scene {scene_id} has only {len(regions)} regions - this may be incomplete")
                
                # Log available region names for debugging
                logger.debug(f"Scene {scene_id} region names: {list(regions.keys())}")
            
            logger.info("Region mapping loaded", 
                       data_file=data_file,
                       scenes=len(self.region_mapping),
                       total_regions=sum(len(regions) for regions in self.region_mapping.values()),
                       scene_ids=list(self.region_mapping.keys()))
            
        except Exception as e:
            logger.error("Failed to load region mapping", error=str(e))
            self.region_mapping = {}
    
    def update_region_count(self, scene_id: str, region_uuid: str, counts: Dict[str, int]):
        """Update count data for a specific region."""
        self.region_counts[region_uuid] = {
            'vehicle': counts.get('vehicle', 0),
            'pedestrian': counts.get('pedestrian', 0),
            'timestamp': datetime.now(timezone.utc)
        }
        logger.debug("Updated region count", 
                    scene_id=scene_id, 
                    region_uuid=region_uuid[:8] + "...", 
                    counts=counts)
    
    def _calculate_directional_density(self, scene_id: str, direction: str, count_type: str = 'vehicle') -> int:
        """Calculate traffic density for a specific direction."""
        if scene_id not in self.region_mapping:
            return 0
        
        region_names = self.TRAFFIC_FORMULAS.get(direction, [])
        total_count = 0
        
        for region_name in region_names:
            if region_name in self.region_mapping[scene_id]:
                region_uuid = self.region_mapping[scene_id][region_name]['uuid']
                if region_uuid in self.region_counts:
                    total_count += self.region_counts[region_uuid].get(count_type, 0)
        
        return total_count
    
    def get_intersection_directional_data(self, scene_id: str, intersection_name: str = None) -> Optional[DirectionalTrafficData]:
        """Get directional traffic data for a specific intersection."""
        # Validate scene ID
        if not self.validate_scene_id(scene_id):
            logger.warning(f"Invalid scene ID requested: {scene_id}")
            return None
        
        # Get coordinates and name from predefined mapping
        coord_info = self.INTERSECTION_COORDINATES.get(scene_id)
        if coord_info:
            latitude = coord_info['latitude']
            longitude = coord_info['longitude']
            if not intersection_name:
                intersection_name = coord_info['name']
        else:
            # Fallback coordinates (default San Francisco Bay Area location)
            latitude = 37.73789
            longitude = -122.40806
            if not intersection_name:
                # Generate name dynamically based on scene position
                scene_index = list(sorted(self.region_mapping.keys())).index(scene_id) + 1
                intersection_name = f"Intersection-{scene_index}"
        
        # Calculate directional densities
        northbound = self._calculate_directional_density(scene_id, 'northbound')
        southbound = self._calculate_directional_density(scene_id, 'southbound')
        eastbound = self._calculate_directional_density(scene_id, 'eastbound')
        westbound = self._calculate_directional_density(scene_id, 'westbound')
        
        # Get current region counts for this scene
        scene_region_counts = {}
        if scene_id in self.region_mapping:
            for region_info in self.region_mapping[scene_id].values():
                region_uuid = region_info['uuid']
                if region_uuid in self.region_counts:
                    scene_region_counts[region_uuid] = {
                        'vehicle': self.region_counts[region_uuid].get('vehicle', 0),
                        'pedestrian': self.region_counts[region_uuid].get('pedestrian', 0)
                    }
        
        return DirectionalTrafficData(
            intersection_id=scene_id,
            intersection_name=intersection_name,
            latitude=latitude,
            longitude=longitude,
            timestamp=datetime.now(timezone.utc),
            northbound_density=northbound,
            southbound_density=southbound,
            eastbound_density=eastbound,
            westbound_density=westbound,
            total_density=northbound + southbound + eastbound + westbound,
            region_counts=scene_region_counts
        )
    
    def get_all_intersections_directional_summary(self) -> IntersectionDirectionalSummary:
        """Get directional traffic summary for all intersections."""
        intersections_data = []
        
        # Get data for each intersection (dynamically from loaded scenes)
        for i, scene_id in enumerate(sorted(self.region_mapping.keys()), 1):
            # Generate intersection name dynamically
            intersection_name = f"Intersection-{i}"
            intersection_data = self.get_intersection_directional_data(scene_id, intersection_name)
            intersections_data.append(intersection_data)
        
        # Calculate overall totals
        overall_northbound = sum(data.northbound_density for data in intersections_data)
        overall_southbound = sum(data.southbound_density for data in intersections_data)
        overall_eastbound = sum(data.eastbound_density for data in intersections_data)
        overall_westbound = sum(data.westbound_density for data in intersections_data)
        
        return IntersectionDirectionalSummary(
            timestamp=datetime.now(timezone.utc),
            total_intersections=len(intersections_data),
            intersections=intersections_data,
            overall_northbound=overall_northbound,
            overall_southbound=overall_southbound,
            overall_eastbound=overall_eastbound,
            overall_westbound=overall_westbound,
            overall_total=overall_northbound + overall_southbound + overall_eastbound + overall_westbound
        )
    
    def get_region_mapping_info(self) -> Dict[str, Any]:
        """Get region mapping information for debugging."""
        return {
            'scenes': len(self.region_mapping),
            'mapping': self.region_mapping,
            'current_counts': len(self.region_counts),
            'formulas': self.TRAFFIC_FORMULAS
        }
    
    def get_available_scenes(self) -> List[Dict[str, Any]]:
        """Get list of available scenes with their information."""
        scenes = []
        for i, scene_id in enumerate(sorted(self.region_mapping.keys()), 1):
            # Get coordinates and name from predefined mapping
            coord_info = self.INTERSECTION_COORDINATES.get(scene_id, {})
            
            scene_info = {
                'scene_id': scene_id,
                'intersection_name': coord_info.get('name', f"Intersection-{i}"),
                'latitude': coord_info.get('latitude', 37.73789),
                'longitude': coord_info.get('longitude', -122.40806),
                'region_count': len(self.region_mapping[scene_id]),
                'regions': list(self.region_mapping[scene_id].keys())
            }
            scenes.append(scene_info)
        return scenes
    
    def validate_scene_id(self, scene_id: str) -> bool:
        """Validate if a scene ID exists in the loaded data."""
        return scene_id in self.region_mapping
    
    def get_scene_region_info(self, scene_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed region information for a specific scene."""
        if not self.validate_scene_id(scene_id):
            return None
        
        regions = self.region_mapping[scene_id]
        region_info = {
            'scene_id': scene_id,
            'total_regions': len(regions),
            'regions': {}
        }
        
        for region_name, region_data in regions.items():
            region_info['regions'][region_name] = {
                'uuid': region_data['uuid'],
                'pk': region_data['pk'],
                'has_current_data': region_data['uuid'] in self.region_counts
            }
        
        return region_info
