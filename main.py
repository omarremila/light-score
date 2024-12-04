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


def get_building_data(lat: float, lng: float, direction: str):
    # Use class variables for caching
    if not hasattr(get_building_data, "_cached_gdf"):
        get_building_data._cached_gdf = None
        get_building_data._cache_file = os.path.join(
            tempfile.gettempdir(), "toronto_buildings.pkl"
        )
        get_building_data._last_download = None
    try:
        # Use the cached GeoDataFrame for calculations
        gdf = get_building_data._cached_gdf
        point = Point(lng, lat)

        # Increased buffer size for initial search
        buffer_distance = 0.01  # Approximately 1km

        # Use spatial index for initial filtering
        bounds = point.buffer(buffer_distance).bounds
        possible_matches_idx = list(gdf.sindex.intersection(bounds))

        if not possible_matches_idx:
            # If no matches found, try with an even larger buffer
            buffer_distance = 0.02  # Approximately 2km
            bounds = point.buffer(buffer_distance).bounds
            possible_matches_idx = list(gdf.sindex.intersection(bounds))

            if not possible_matches_idx:
                print(
                    f"No buildings found within {buffer_distance} degrees of {lat}, {lng}"
                )
                return None

        possible_matches = gdf.iloc[possible_matches_idx]

        # Quick filter using centroid coordinates
        mask = {
            "N": possible_matches["centroid_y"] > lat,
            "S": possible_matches["centroid_y"] < lat,
            "E": possible_matches["centroid_x"] > lng,
            "W": possible_matches["centroid_x"] < lng,
        }[direction]

        direction_filtered = possible_matches[mask]

        if direction_filtered.empty:
            print(f"No buildings found in direction {direction} from {lat}, {lng}")
            return None

        # Calculate approximate distances using centroids
        direction_filtered["approx_distance"] = (
            (
                (direction_filtered["centroid_x"] - lng) ** 2
                + (direction_filtered["centroid_y"] - lat) ** 2
            )
            ** 0.5
        ) * 111000  # Convert to meters

        # Get top candidates and calculate exact distances
        # Increased number of candidates to check
        top_candidates = direction_filtered.nsmallest(10, "approx_distance")

        # Use the same buffer distance for final check
        within_buffer = top_candidates[
            top_candidates.geometry.within(point.buffer(buffer_distance))
        ]

        if within_buffer.empty:
            print(f"No buildings within final buffer of {buffer_distance} degrees")
            return None

        within_buffer["distance"] = within_buffer.geometry.distance(point) * 111000
        closest = within_buffer.sort_values("distance").iloc[0]

        result = {
            "height": float(closest["height"]),
            "distance": float(closest["distance"]),
        }
        print(f"Found building: {result}")
        return result

    except Exception as e:
        print(f"Error in processing: {e}")
        if get_building_data._cached_gdf is not None:
            get_building_data._cached_gdf = None
            try:
                return get_building_data(lat, lng, direction)
            except:
                pass
        return None


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
