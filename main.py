from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests
import geopandas as gpd
from shapely.geometry import Point
import logging
import math
import debugpy
import os
import pickle
from concurrent.futures import ThreadPoolExecutor, as_completed
import tempfile
import fiona
from shapely.geometry import shape  # This is also needed for the shape() function
import os

# Only enable debugger when running in debug mode
if not debugpy.is_client_connected():
    debugpy.listen(("localhost", 5678))
    print("⚡ Debugger is listening on port 5678")
app = FastAPI()
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import geopandas as gpd
from shapely.geometry import Point

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://sun-light-strength.up.railway.app",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
            buildings_list.append(
                {
                    "distance": round(building["distance"], 1),
                    "height_max": round(float(building["MAX_HEIGHT"]), 1),
                    "height": round(float(building["HEIGHT_MSL"]), 1),
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
        print(f"Error: {str(e)}")
        import traceback

        traceback.print_exc()
        return None


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




def calculate_light_score(building_data: dict, floor: int, direction: str):
    if not building_data:
        return {"score": 95, "reason": "No buildings found"}

    relative_height = building_data["height"] - (floor * 3)
    angle = math.degrees(math.atan2(relative_height, building_data["distance"]))

    if direction == "S":
        if angle < 15:
            score = 95
        elif angle > 45:
            score = 40
        else:
            score = 95 - ((angle - 15) * 1.8)
    else:
        if angle < 20:
            score = 90
        elif angle > 60:
            score = 50
        else:
            score = 90 - ((angle - 20) * 1)

    direction_weights = {"S": 1.0, "E": 0.85, "W": 0.85, "N": 0.7}
    score *= direction_weights.get(direction, 1.0)

    floor_bonus = min(floor * 2, 20) if floor > 1 else 0
    final_score = min(100, score + floor_bonus)

    return {
        "score": round(final_score, 1),
        "building_height": round(building_data["height"]),
        "building_distance": round(building_data["distance"]),
        "angle": round(angle, 1),
        "floor_bonus": floor_bonus,
    }


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
    if direction not in ["N", "S", "E", "W", "NE", "NW", "SE", "SW"]:
        raise HTTPException(status_code=400, detail="Invalid direction")

    address = f"{streetNumber} {streetName}, {city}, {postalCode}, {country}"
    lat, lng = geocode_address(address)

    if not lat or not lng:
        raise HTTPException(status_code=404, detail="Address not found")

    building_data = find_nearby_buildings(lat, lng, direction)
    filtered_buildings = filter_by_direction(building_data, lat, lng, direction)
    score_data = calculate_light_score(filtered_buildings, floor, direction)

    return {
        "coordinates": {"lat": lat, "lng": lng},
        "light_score": score_data["score"],
        "details": score_data,
        "building_data": building_data,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)



