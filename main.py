# FastAPI and web-related
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests

# Geospatial libraries
import geopandas as gpd
from shapely.geometry import Point, shape
import fiona

# Scientific and mathematical
import astropy.coordinates as coord
from astropy.time import Time
import astropy.units as u
import math

# System and utilities (only once)
import os
import debugpy
import logging

# Logging setup
class IndexFilter(logging.Filter):
    def filter(self, record):
        return 'Next index' not in record.getMessage()

# Set up root logger with filter
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
root_logger = logging.getLogger()
root_logger.addFilter(IndexFilter())

# Initialize logger for this module
logger = logging.getLogger(__name__)

# Set Fiona's logger level
logging.getLogger('fiona.collection').setLevel(logging.WARNING)
logging.getLogger('fiona').addFilter(IndexFilter())

# Then FastAPI app initialization
app = FastAPI()
@app.get("/health")
async def health_check():
    return {"status": "healthy"}
# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://sun-light-strength.up.railway.app/", "https://light-score-production.up.railway.app/"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


import math

def validate_environment():
    required_vars = ["LOCATIONIQ_API_KEY"]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

def calculate_azimuth(lat1, lon1, lat2, lon2):
    # Convert decimal degrees to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dlon = lon2_rad - lon1_rad

    y = math.sin(dlon) * math.cos(lat2_rad)
    x = math.cos(lat1_rad) * math.sin(lat2_rad) - \
        math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon)

    bearing_rad = math.atan2(y, x)
    bearing_deg = math.degrees(bearing_rad)

    # Normalize to [0, 360) degrees
    bearing_deg = (bearing_deg + 360) % 360

    return bearing_deg

def geocode_address(address: str):

    api_key = os.getenv("LOCATIONIQ_API_KEY") 

    base_url = "https://us1.locationiq.com/v1/search.php"
    params = {"key": api_key, "q": address, "format": "json", "limit": 1}

    try:
        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data and isinstance(data, list) and len(data) > 0:
            return float(data[0]["lat"]), float(data[0]["lon"])
        return None, None
    except Exception as e:
        return None, None



def find_nearby_buildings(lat: float, lng: float, radius_meters: float = 100):
    """
    Find buildings within specified radius of a given location.

    Args:
        lat (float): Latitude of the search point
        lng (float): Longitude of the search point
        radius_meters (float): Search radius in meters (default 500m)
    """
    DEBUG = False
    try:
        if DEBUG:
            print(f"Searching for buildings near {lat}, {lng}...")

        # Load the shapefile
        buildings = gpd.read_file("data/3DMassingShapefile_2023_WGS84.shp")

        # Filter buildings roughly within the area first using lat/long columns
        # Convert radius to approximate degrees (1 degree ~ 111km at equator)
        degree_radius = radius_meters / 111000

        mask = (
            (buildings["LATITUDE"] >= lat - degree_radius)
            & (buildings["LATITUDE"] <= lat + degree_radius)
            & (buildings["LONGITUDE"] >= lng - degree_radius)
            & (buildings["LONGITUDE"] <= lng + degree_radius)
        )

        nearby = buildings[mask].copy()

        if len(nearby) == 0:
            print("No buildings found in initial search area")
            return []

        # Calculate exact distances for the filtered buildings
        search_point = Point(lng, lat)
        nearby["distance"] = nearby.apply(
            lambda row: Point(row["LONGITUDE"], row["LATITUDE"]).distance(search_point)
            * 111000,
            axis=1,
        )

        # Filter by exact distance and sort
        result = nearby[nearby["distance"] <= radius_meters].sort_values("distance")

        # Convert to list of dictionaries for output
        buildings_list = []

        for _, building in result.iterrows():
            height_values = [
                building.get("MIN_HEIGHT", 0),
                building.get("MAX_HEIGHT", 0), 
                building.get("AVG_HEIGHT", 0),
                building.get("HEIGHT_MSL", 0)
            ]
            buildings_list.append(
                {
                    "distance": round(building["distance"], 1),
                    "height": round(float(max(height_values)), 1),
                    "area": round(float(building["SHAPE_AREA"]), 1),
                    "lat": building["LATITUDE"],
                    "lng": building["LONGITUDE"],
                }
            )
        if DEBUG:
            print(f"Found {len(buildings_list)} buildings within {radius_meters}m")
            # Print first few results
            for building in buildings_list:
                print(
                    f"Building at {building['distance']}m: "
                    f"Height={building['height']}m, "
                    f"Area={building['area']}m²"
                    f"lat= {building["lat"]}"
                    f"lng=  {building["lng"]}"
                )

        return buildings_list

    except Exception as e:
        logger.error(f"Error finding nearby buildings: {str(e)}")
        return []


def filter_by_direction(buildings_list, origin_lat, origin_lng, direction):
    """
    Filter buildings list based on direction relative to origin point.

    Args:
        buildings_list: List of buildings with 'lat' and 'lng' keys
        origin_lat: Latitude of reference point
        origin_lng: Longitude of reference point
        direction: "N", "NE", "E", "SE", "S", "SW", "W", or "NW"

    Returns:
        List of buildings in specified direction
    """
    filtered_buildings = []
    
    for building in buildings_list:
        lat_diff = building['lat'] - origin_lat
        lng_diff = building['lng'] - origin_lng
        
        is_in_direction = False
        
        # Simple direction checks
        if direction == "N" and lat_diff > 0:
            is_in_direction = True
        elif direction == "S" and lat_diff < 0:
            is_in_direction = True
        elif direction == "E" and lng_diff > 0:
            is_in_direction = True
        elif direction == "W" and lng_diff < 0:
            is_in_direction = True
        # Diagonal checks
        elif direction == "NE" and lat_diff > 0 and lng_diff > 0:
            is_in_direction = True
        elif direction == "SE" and lat_diff < 0 and lng_diff > 0:
            is_in_direction = True
        elif direction == "SW" and lat_diff < 0 and lng_diff < 0:
            is_in_direction = True
        elif direction == "NW" and lat_diff > 0 and lng_diff < 0:
            is_in_direction = True
            
        if is_in_direction:
            filtered_buildings.append(building)
    
    return filtered_buildings



def get_sun_position(latitude: float, longitude: float, time: Time = None):
    """
    Get both sun angle and azimuth.
    """
    location = coord.EarthLocation(lon=longitude * u.deg, lat=latitude * u.deg)

    if time is None:
        time = Time.now()

    altaz = coord.AltAz(location=location, obstime=time)
    sun = coord.get_sun(time)
    sun_altaz = sun.transform_to(altaz)

    return {"elevation": float(sun_altaz.alt.deg), "azimuth": float(sun_altaz.az.deg)}


def calculate_obstruction_factor(buildings: list, floor: int) -> float:
    """
    Calculate the obstruction factor based on surrounding buildings.
    
    Mathematical components:
    1. Angular Height (θ) = arctan((building_height - observer_height) / distance)
    2. Distance Weight (w) = 1 / (1 + d/100) where d is distance in meters
    3. Total Obstruction = Σ(θ_i * w_i) for each building i
    4. Obstruction Factor = max(0, min(1, 1 - (total_obstruction / 360)))
    
    Parameters:
        buildings: List of dictionaries containing building data
        floor: Observer's floor number
    """
    if not buildings:
        return 1.0
        
    floor_height = 3  # meters per floor
    observer_height = floor * floor_height
    total_obstruction = 0
    max_obstruction = 360  # degrees in a circle
    
    logger.info(f"\n=== Starting Obstruction Factor Calculation ===")
    logger.info(f"Observer floor: {floor}, height: {observer_height}m")
    logger.info(f"Number of buildings to analyze: {len(buildings)}")
    
    for idx, building in enumerate(buildings, 1):
        logger.info(f"\nAnalyzing building #{idx}:")
        logger.info(f"Building height: {building['height']}m, distance: {building['distance']}m")
        
        # 1. Calculate height difference
        building_height_diff = building['height'] - observer_height
        logger.info(f"Height difference: {building_height_diff}m")
        
        if building_height_diff > 0:
            distance = building['distance']
            
            # 2. Calculate angular height (θ)
            # Using arctangent to find angle between horizontal and line to top of building
            angle = math.degrees(math.atan2(building_height_diff, distance))
            
            # 3. Calculate distance weight
            # Buildings closer have more impact (inverse relationship with distance)
            weight = 1 / (1 + distance/100)  # Normalize to 0-1 range
            
            # 4. Add weighted obstruction to total
            total_obstruction += angle * weight
    
    # 5. Normalize to 0-1 range
    obstruction_factor = max(0, min(1, 1 - (total_obstruction / max_obstruction)))
    logger.info(f"\nFinal Calculations:")
    logger.info(f"Total obstruction: {total_obstruction:.2f}°")
    logger.info(f"Normalized obstruction factor: {obstruction_factor:.2f}")
    logger.info("=== Obstruction Factor Calculation Complete ===\n")
    return round(obstruction_factor, 2)

def calculate_sun_blockage(sun_angle: float, sun_azimuth: float, buildings: list, 
                        observer_lat: float, observer_lng: float, floor: int):
    logger.info(f"\n=== Starting Sun Blockage Calculation ===")
    logger.info(f"Sun angle: {sun_angle}°, Sun azimuth: {sun_azimuth}°")
    logger.info(f"Observer position: {observer_lat:.4f}°N, {observer_lng:.4f}°E, Floor: {floor}")
    """
    Calculate sun blockage based on building positions and sun angle.
    
    Mathematical components:
    1. Building Angular Height (θ_b) = arctan((building_height - observer_height) / distance)
    2. Sun Angular Height (θ_s) = sun_angle
    3. Building Azimuth (α_b) = arctan2(building_lng - observer_lng, building_lat - observer_lat)
    4. Azimuth Difference (Δα) = |α_b - sun_azimuth|
    5. Blockage Impact = (θ_b - θ_s) * (15 - Δα)/15 when Δα < 15°
    
    Parameters:
        sun_angle: Solar elevation angle in degrees
        sun_azimuth: Solar azimuth angle in degrees
        buildings: List of buildings with height and position data
        observer_lat/lng: Observer's coordinates
        floor: Observer's floor number
    """
    try:
        blockage = {
            "is_blocked": False,
            "blockage_percentage": 0,
            "blocking_buildings": []
        }
        
        if not buildings:
            return blockage
            
        floor_height = 3  # meters per floor
        observer_height = floor * floor_height
        
        for building in buildings:
            # 1. Calculate relative height
            building_height_diff = building['height'] - observer_height
            
            if building_height_diff > 0:  # Only consider taller buildings
                distance = building['distance']
                
                # 2. Calculate building's angular height
                building_angle = math.degrees(math.atan2(building_height_diff, distance))
                # 3. Calculate building's azimuth relative to observer
                building_azimuth = calculate_azimuth(building['lng'], building['lat'], observer_lat, observer_lng)
                logger.info(f"LAT: {building['lat']} LONG: {str(building['lng'])}°")
                logger.info(f"LAT: {observer_lat} LONG: {str(observer_lng)}°")
                logger.info(f"Building angle: {building_angle}°, Building azimuth: {str(building_azimuth)}°")
                logger.info(f"Building angle : {calculate_azimuth(building['lng'], building['lat'], observer_lat, observer_lng)}")
                # 4. Calculate azimuth difference``
                azimuth_diff = abs(building_azimuth - sun_azimuth)
                if azimuth_diff > 180:
                    azimuth_diff = 360 - azimuth_diff
                    
                # 5. If building is in sun's path (within 15 degrees)
                if azimuth_diff < 15:
                    # If building angle is greater than sun angle, sun is blocked
                    if building_angle > sun_angle:
                        blockage["is_blocked"] = True
                        
                        # Calculate blockage impact
                        impact = (building_angle - sun_angle) * (15 - azimuth_diff) / 15
                        blockage["blockage_percentage"] = min(100, 
                            blockage["blockage_percentage"] + impact)
                    
                        blockage["blocking_buildings"].append({
                            "distance": building["distance"],
                            "height": building["height"],
                            "angle": building_angle,
                            "azimuth_diff": azimuth_diff,
                            "impact": impact
                        })
        
        return blockage
    except Exception as e:
        logger.error(f"Error calculating sun blockage: {str(e)}")
        return {"is_blocked": False, "blockage_percentage": 0, "blocking_buildings": []}

def calculate_final_score(base_score: float, floor: int, direction: str, 
                        sun_blockage: dict, obstruction_factor: float) -> float:
    logger.info(f"\n=== Starting Final Score Calculation ===")
    logger.info(f"Initial base score: {base_score}")
    logger.info(f"Floor: {floor}, Direction: {direction}")
    logger.info(f"Sun blockage: {sun_blockage['blockage_percentage']}%")
    logger.info(f"Obstruction factor: {obstruction_factor}")
    """
    Calculate final light score incorporating all factors.
    
    Mathematical components:
    1. Base Score Adjustment: base_score * obstruction_factor
    2. Floor Bonus: min(floor * 2, 20)
    3. Direction Factor: Multiplier based on orientation
    4. Final Score = min(100, (adjusted_base_score * direction_factor) + floor_bonus)
    
    Parameters:
        base_score: Initial score before adjustments
        floor: Building floor number
        direction: Orientation of the window
        sun_blockage: Dictionary containing sun blockage calculations
        obstruction_factor: Factor representing general obstruction
    """
    # 1. Apply obstruction factor to base score
    adjusted_base_score = base_score * obstruction_factor
    
    # 2. Calculate floor bonus (2 points per floor, max 20)
    floor_bonus = min(floor * 2, 20) if floor > 1 else 0
    
    # 3. Direction factors (South-facing is optimal)
    direction_factors = {
        "S": 1.0,    # South: 100% optimal
        "SE": 0.9,   # Southeast: 90% optimal
        "SW": 0.9,   # Southwest: 90% optimal
        "E": 0.8,    # East: 80% optimal
        "W": 0.8,    # West: 80% optimal
        "NE": 0.7,   # Northeast: 70% optimal
        "NW": 0.7,   # Northwest: 70% optimal
        "N": 0.6     # North: 60% optimal
    }
    
    # 4. Calculate final score
    final_score = min(100, (adjusted_base_score * direction_factors[direction]) + floor_bonus)
    return round(final_score, 1)
@app.get("/")
async def root():
    return {"status": "ok"}
@app.get("/light_score/")
async def get_light_score(
    country: str,
    city: str,
    postalCode: str,
    streetName: str,
    streetNumber: str,
    floor: int = 1,
    direction: str = "S",
):
    logger.info(f"\n\n=== New Light Score Request ===")
    logger.info(f"Address: {streetNumber} {streetName}, {city}, {postalCode}, {country}")
    logger.info(f"Floor: {floor}, Direction: {direction}")
    
    if direction not in ["N", "S", "E", "W", "NE", "NW", "SE", "SW"]:
        logger.error(f"Invalid direction: {direction}")
        raise HTTPException(status_code=400, detail="Invalid direction")

    # Geocode address
    address = f"{streetNumber} {streetName}, {city}, {postalCode}, {country}"
    lat, lng = geocode_address(address)
    logger.info(f"Geocoded coordinates: {lat}, {lng}")

    if not lat or not lng:
        logger.error(f"Address not found: {address}")
        raise HTTPException(status_code=404, detail="Address not found")

    # Get nearby buildings
    buildings = find_nearby_buildings(lat, lng)
    buildings= filter_by_direction(buildings, lat, lng, direction)
    logger.info(f"Found {len(buildings)} nearby buildings")
    
    # Get sun position
    sun_position = get_sun_position(lat, lng)
    logger.info(f"Sun position - Elevation: {sun_position['elevation']}°, Azimuth: {sun_position['azimuth']}°")
    
    # Calculate sun blockage
    sun_blockage = calculate_sun_blockage(
        sun_position["elevation"],
        sun_position["azimuth"],
        buildings,
        lat,
        lng,
        floor
    )
    
    # Calculate obstruction factor
    obstruction_factor = calculate_obstruction_factor(buildings, floor)
    
    # Calculate final score
    base_score = 85 - (sun_blockage["blockage_percentage"] * 0.5)
    final_score = calculate_final_score(base_score, floor, direction, sun_blockage, obstruction_factor)
    
    logger.info(f"\nFinal Results:")
    logger.info(f"Base Score: {base_score:.1f}")
    logger.info(f"Sun Blockage: {sun_blockage['blockage_percentage']:.1f}%")
    logger.info(f"Obstruction Factor: {obstruction_factor:.2f}")
    logger.info(f"Final Light Score: {final_score}\n")
    logger.info("=== Request Complete ===\n")

    return {
        "coordinates": {"lat": lat, "lng": lng},
        "light_score": round(final_score, 1),
        "details": {
            "base_score": round(base_score, 1),
            "floor_bonus": min(floor * 2, 20) if floor > 1 else 0,
            "direction": direction,
            "sun_blockage": sun_blockage,
            "obstruction_factor": obstruction_factor
        },
        "sun_position": sun_position,
        "building_data": buildings
    }
if __name__ == "__main__":
    validate_environment()
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)



