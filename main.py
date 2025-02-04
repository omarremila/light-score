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

from dotenv import load_dotenv

load_dotenv()  # This should be at the top of your file, before any environment variables are accessed


# Logging setup
class IndexFilter(logging.Filter):
    def filter(self, record):
        return "Next index" not in record.getMessage()


# Set up root logger with filter
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
root_logger = logging.getLogger()
root_logger.addFilter(IndexFilter())

# Initialize logger for this module
logger = logging.getLogger(__name__)

# Set Fiona's logger level
logging.getLogger("fiona.collection").setLevel(logging.WARNING)
logging.getLogger("fiona").addFilter(IndexFilter())

# Then FastAPI app initialization
app = FastAPI()
# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    logger.info("Root endpoint called")
    # Test environment variables
    api_key = os.getenv("LOCATIONIQ_API_KEY")
    logger.info(f"api key {api_key}")
    try:
        # Test shapefile access
        shapefile_path = "data/3DMassingShapefile_2023_WGS84.shp"
        if not os.path.exists(shapefile_path):
            logger.error("Shapefile missing")
            return {"status": "error", "detail": "Shapefile missing"}

        if not os.getenv("LOCATIONIQ_API_KEY"):
            logger.error("API key missing")
            return {"status": "error", "detail": "API key missing"}

        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error in root endpoint: {str(e)}")
        return {"status": "error", "detail": str(e)}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/geocode")
async def geocode(address: str):
    lat, lng = geocode_address(address)
    if not lat or not lng:
        raise HTTPException(status_code=404, detail="Address not found")
    return {"lat": lat, "lng": lng}


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
    logger.info(
        f"Address: {streetNumber} {streetName}, {city}, {postalCode}, {country}"
    )
    logger.info(f"Floor: {floor}, Direction: {direction}")

    # Validate direction input
    if direction.upper() not in ["N", "S", "E", "W", "NE", "NW", "SE", "SW"]:
        logger.error(f"Invalid direction: {direction}")
        raise HTTPException(status_code=400, detail="Invalid direction")

    # Geocode address
    full_address = f"{streetNumber} {streetName}, {city}, {postalCode}, {country}"
    lat, lng = geocode_address(full_address)
    logger.info(f"Geocoded coordinates: {lat}, {lng}")

    if not lat or not lng:
        logger.error(f"Address not found: {full_address}")
        raise HTTPException(status_code=404, detail="Address not found")

    # Calculate dynamic light score (using the new function)
    dynamic_score = calculate_dynamic_light_score(lat, lng, floor, direction)

    # Optionally, get extra details for the response
    sun_position = get_sun_position(lat, lng)
    buildings = find_nearby_buildings(lat, lng)

    logger.info(f"\nFinal Light Score: {dynamic_score}\n")
    logger.info("=== Request Complete ===\n")

    return {
        "coordinates": {"lat": lat, "lng": lng},
        "light_score": dynamic_score,
        "details": {
            "floor": floor,
            "direction": direction,
            "sun_position": sun_position,
            "building_data": buildings,
        },
    }


def validate_environment():
    required_vars = ["LOCATIONIQ_API_KEY"]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}"
        )


def calculate_azimuth(lat1, lon1, lat2, lon2):
    # Convert decimal degrees to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dlon = lon2_rad - lon1_rad

    y = math.sin(dlon) * math.cos(lat2_rad)
    x = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(
        lat2_rad
    ) * math.cos(dlon)

    bearing_rad = math.atan2(y, x)
    bearing_deg = math.degrees(bearing_rad)

    # Normalize to [0, 360) degrees
    bearing_deg = (bearing_deg + 360) % 360

    return bearing_deg


def geocode_address(address: str):
    api_key = os.getenv("LOCATIONIQ_API_KEY")
    logger.info(f"api key {api_key}")
    print(f"api key {api_key}", flush=True)

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
    """
    DEBUG = False
    try:
        if DEBUG:
            print(f"Searching for buildings near {lat}, {lng}...")

        # Load the shapefile
        buildings = gpd.read_file("data/3DMassingShapefile_2023_WGS84.shp")
        logger.info(f"Directory contents: {os.listdir()}")

        if not os.path.exists("data/3DMassingShapefile_2023_WGS84.shp"):
            logger.error(f"Shapefile not found :(")
            return []

        # Filter buildings roughly within the area using lat/long columns
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
                building.get("HEIGHT_MSL", 0),
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

        return buildings_list

    except Exception as e:
        logger.error(f"Error finding nearby buildings: {str(e)}")
        return []


def filter_by_direction(buildings_list, origin_lat, origin_lng, direction):
    """
    Filter buildings list based on direction relative to origin point.
    """
    filtered_buildings = []

    for building in buildings_list:
        lat_diff = building["lat"] - origin_lat
        lng_diff = building["lng"] - origin_lng

        is_in_direction = False

        # Simple direction checks
        if direction.upper() == "N" and lat_diff > 0:
            is_in_direction = True
        elif direction.upper() == "S" and lat_diff < 0:
            is_in_direction = True
        elif direction.upper() == "E" and lng_diff > 0:
            is_in_direction = True
        elif direction.upper() == "W" and lng_diff < 0:
            is_in_direction = True
        # Diagonal checks
        elif direction.upper() == "NE" and lat_diff > 0 and lng_diff > 0:
            is_in_direction = True
        elif direction.upper() == "SE" and lat_diff < 0 and lng_diff > 0:
            is_in_direction = True
        elif direction.upper() == "SW" and lat_diff < 0 and lng_diff < 0:
            is_in_direction = True
        elif direction.upper() == "NW" and lat_diff > 0 and lng_diff < 0:
            is_in_direction = True

        if is_in_direction:
            filtered_buildings.append(building)

    return filtered_buildings


def get_sun_position(latitude: float, longitude: float, time: Time = None):
    """
    Get both sun elevation and azimuth.
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
        logger.info(
            f"Building height: {building['height']}m, distance: {building['distance']}m"
        )

        # 1. Calculate height difference
        building_height_diff = building["height"] - observer_height
        logger.info(f"Height difference: {building_height_diff}m")

        if building_height_diff > 0:
            distance = building["distance"]

            # 2. Calculate angular height (θ)
            angle = math.degrees(math.atan2(building_height_diff, distance))

            # 3. Calculate distance weight
            weight = 1 / (1 + distance / 100)  # Normalize to 0-1 range

            total_obstruction += angle * weight

    obstruction_factor = max(0, min(1, 1 - (total_obstruction / max_obstruction)))
    logger.info(f"\nFinal Calculations:")
    logger.info(f"Total obstruction: {total_obstruction:.2f}°")
    logger.info(f"Normalized obstruction factor: {obstruction_factor:.2f}")
    logger.info("=== Obstruction Factor Calculation Complete ===\n")
    return round(obstruction_factor, 2)


def calculate_sun_blockage(
    sun_angle: float,
    sun_azimuth: float,
    buildings: list,
    observer_lat: float,
    observer_lng: float,
    floor: int,
):
    logger.info(f"\n=== Starting Sun Blockage Calculation ===")
    logger.info(f"Sun angle: {sun_angle}°, Sun azimuth: {sun_azimuth}°")
    logger.info(
        f"Observer position: {observer_lat:.4f}°N, {observer_lng:.4f}°E, Floor: {floor}"
    )
    """
    Calculate sun blockage based on building positions and sun angle.
    """
    try:
        blockage = {
            "is_blocked": False,
            "blockage_percentage": 0,
            "blocking_buildings": [],
        }

        if not buildings:
            return blockage

        floor_height = 3  # meters per floor
        observer_height = floor * floor_height

        for building in buildings:
            building_height_diff = building["height"] - observer_height

            if building_height_diff > 0:
                distance = building["distance"]

                building_angle = math.degrees(
                    math.atan2(building_height_diff, distance)
                )
                building_azimuth = calculate_azimuth(
                    building["lng"], building["lat"], observer_lat, observer_lng
                )
                logger.info(f"LAT: {building['lat']} LONG: {str(building['lng'])}°")
                logger.info(f"LAT: {observer_lat} LONG: {str(observer_lng)}°")
                logger.info(
                    f"Building angle: {building_angle}°, Building azimuth: {str(building_azimuth)}°"
                )
                azimuth_diff = abs(building_azimuth - sun_azimuth)
                if azimuth_diff > 180:
                    azimuth_diff = 360 - azimuth_diff

                if azimuth_diff < 15:
                    if building_angle > sun_angle:
                        blockage["is_blocked"] = True
                        impact = (building_angle - sun_angle) * (15 - azimuth_diff) / 15
                        blockage["blockage_percentage"] = min(
                            100, blockage["blockage_percentage"] + impact
                        )
                        blockage["blocking_buildings"].append(
                            {
                                "distance": building["distance"],
                                "height": building["height"],
                                "angle": building_angle,
                                "azimuth_diff": azimuth_diff,
                                "impact": impact,
                            }
                        )

        return blockage
    except Exception as e:
        logger.error(f"Error calculating sun blockage: {str(e)}")
        return {"is_blocked": False, "blockage_percentage": 0, "blocking_buildings": []}


def calculate_final_score(
    base_score: float,
    floor: int,
    direction: str,
    sun_blockage: dict,
    obstruction_factor: float,
) -> float:
    logger.info(f"\n=== Starting Final Score Calculation ===")
    logger.info(f"Initial base score: {base_score}")
    logger.info(f"Floor: {floor}, Direction: {direction}")
    logger.info(f"Sun blockage: {sun_blockage['blockage_percentage']}%")
    logger.info(f"Obstruction factor: {obstruction_factor}")
    """
    Calculate final light score incorporating all factors.
    """
    adjusted_base_score = base_score * obstruction_factor
    floor_bonus = min(floor * 2, 20) if floor > 1 else 0

    direction_factors = {
        "S": 1.0,
        "SE": 0.9,
        "SW": 0.9,
        "E": 0.8,
        "W": 0.8,
        "NE": 0.7,
        "NW": 0.7,
        "N": 0.6,
    }

    final_score = min(
        100, (adjusted_base_score * direction_factors[direction.upper()]) + floor_bonus
    )
    return round(final_score, 1)


def calculate_dynamic_light_score(
    lat: float, lng: float, floor: int, direction: str, search_radius: float = 100
) -> float:
    """
    Calculate a dynamic light score using a baseline derived from the sun’s elevation,
    then adjust it by sun blockage, surrounding building obstruction, a floor bonus,
    and a directional multiplier.

    Steps:
      1. Get sun position.
      2. Compute a potential irradiance proxy:
             potential_irradiance = 1000 * sin(sun_elevation in radians)
         which is mapped to a baseline score between 0 and 100.
      3. Get nearby buildings.
      4. Compute sun blockage and a shading penalty.
      5. Compute an obstruction factor.
      6. Add a floor bonus (2 points per floor, max 20) and multiply by a direction factor.
      7. Clamp the final score between 0 and 100.
    """
    # 1. Get sun position
    sun_position = get_sun_position(lat, lng)
    sun_elevation = sun_position["elevation"]
    sun_azimuth = sun_position["azimuth"]

    # 2. Compute dynamic baseline from sun elevation (simple irradiance proxy)
    if sun_elevation > 0:
        potential_irradiance = 1000 * math.sin(math.radians(sun_elevation))
    else:
        potential_irradiance = 0
    dynamic_baseline = (potential_irradiance / 1000) * 100  # Scale to 0-100

    # 3. Get nearby buildings
    buildings = find_nearby_buildings(lat, lng, radius_meters=search_radius)

    # 4. Calculate sun blockage (shading penalty)
    sun_blockage = calculate_sun_blockage(
        sun_elevation, sun_azimuth, buildings, lat, lng, floor
    )
    shading_penalty = sun_blockage["blockage_percentage"]

    # 5. Calculate the obstruction factor
    obstruction_factor = calculate_obstruction_factor(buildings, floor)
    adjusted_score = dynamic_baseline * obstruction_factor

    # 6. Floor bonus and directional multiplier
    floor_bonus = min(floor * 2, 20) if floor > 1 else 0
    direction_factors = {
        "S": 1.0,
        "SE": 0.9,
        "SW": 0.9,
        "E": 0.8,
        "W": 0.8,
        "NE": 0.7,
        "NW": 0.7,
        "N": 0.6,
    }
    direction_multiplier = direction_factors.get(direction.upper(), 1.0)

    # 7. Compute final score: subtract shading penalty, apply multiplier and bonus, and clamp to 0-100
    final_score = (
        (adjusted_score * direction_multiplier) - shading_penalty + floor_bonus
    )
    final_score = max(0, min(final_score, 100))
    return round(final_score, 1)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
