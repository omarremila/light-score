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
    api_key = "pk.68d59be44a490cd6237c99dbe3ff62e2"  # os.getenv("LOCATIONIQ_API_KEY")
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


import fiona
from shapely.geometry import Point, shape
import os


def get_building_data(lat: float, lng: float, direction: str):
    try:
        print("Loading shapefile data...")
        base_dir = os.path.dirname(os.path.abspath(__file__))
        shapefile_path = os.path.join(
            base_dir, "data", "3DMassingShapefile_2023_WGS84.shp"
        )
        print(f"Attempting to load shapefile from: {shapefile_path}")

        if not os.path.exists(shapefile_path):
            print(f"Error: Shapefile not found at {shapefile_path}")
            return None

        with fiona.open(shapefile_path, "r") as source:
            print(f"Successfully opened shapefile. Schema: {source.schema}")
            print(f"Number of records: {len(source)}")

            point = Point(lng, lat)
            print(f"Searching around point: {point}")

            # Convert 500m to degrees (approximately 0.0045 degrees)
            buffer_distance = 0.0045
            search_area = point.buffer(buffer_distance)
            bounds = search_area.bounds
            print(f"Search bounds: {bounds}")

            # List to store nearby buildings
            buildings_list = []
            count = 0

            # Filter and process buildings
            for feature in source:
                count += 1
                if count % 1000 == 0:  # Print progress every 1000 features
                    print(f"Processed {count} features...")

                # Create Shapely geometry from feature
                try:
                    building_geom = shape(feature["geometry"])
                    centroid = building_geom.centroid

                    # Calculate distance in meters
                    distance = (
                        building_geom.distance(point) * 111000
                    )  # Convert to meters

                    if distance <= 500:  # Within 500m
                        height = float(feature["properties"].get("MAX_HEIGHT", 0))
                        print(f"Found building: Distance={distance}m, Height={height}m")
                        buildings_list.append(
                            {
                                "height": height,
                                "distance": distance,
                                "direction": get_direction(
                                    lat, lng, centroid.y, centroid.x
                                ),
                            }
                        )
                except Exception as e:
                    print(f"Error processing feature: {e}")
                    continue

            print(f"Total buildings found within 500m: {len(buildings_list)}")
            if not buildings_list:
                print(f"No buildings found within 500m of {lat}, {lng}")
                return None

            # Sort by distance
            buildings_list.sort(key=lambda x: x["distance"])
            print(f"Closest building: {buildings_list[0]}")

            return buildings_list

    except Exception as e:
        print(f"Error in loading shapefile: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        import traceback

        traceback.print_exc()
        return None


def get_direction(lat1: float, lng1: float, lat2: float, lng2: float) -> str:
    """Calculate the cardinal direction (N,S,E,W) from point 1 to point 2"""
    dlat = lat2 - lat1
    dlng = lng2 - lng1

    if abs(dlat) > abs(dlng):
        return "N" if dlat > 0 else "S"
    else:
        return "E" if dlng > 0 else "W"


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
    if direction not in ["N", "S", "E", "W"]:
        raise HTTPException(status_code=400, detail="Invalid direction")

    address = f"{streetNumber} {streetName}, {city}, {postalCode}, {country}"
    lat, lng = geocode_address(address)

    if not lat or not lng:
        raise HTTPException(status_code=404, detail="Address not found")

    building_data = get_building_data(lat, lng, direction)
    score_data = calculate_light_score(building_data, floor, direction)

    return {
        "coordinates": {"lat": lat, "lng": lng},
        "light_score": score_data["score"],
        "details": score_data,
        "building_data": building_data,
    }


""" 
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

"""


def test_location():
    # Test address: 19 Grand Trunk Crescent
    test_data = {
        "country": "Canada",
        "city": "Toronto",
        "postalCode": "M5J 3A3",
        "streetName": "Grand Trunk Crescent",
        "streetNumber": "19",
        "floor": 5,
        "direction": "S",
    }

    # Create a test client
    from fastapi.testclient import TestClient

    client = TestClient(app)

    # Make the request
    response = client.get("/light_score/", params=test_data)

    print(
        f"\nTesting: 19 Grand Trunk Crescent, Floor {test_data['floor']}, Direction {test_data['direction']}"
    )
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print("\nResults:")
        print(f"Light Score: {data.get('light_score')}")
        print(f"Coordinates: {data.get('coordinates')}")
        print("\nDetails:")
        for key, value in data.get("details", {}).items():
            print(f"{key}: {value}")
        print("\nBuilding Data:")
        print(data.get("building_data"))
    else:
        print("Error:", response.text)


if __name__ == "__main__":
    import uvicorn

    # Add this line to run tests
    test_location()

    # Comment this out during testing if you don't want to start the server
    # uvicorn.run(app, host="0.0.0.0", port=8000)
