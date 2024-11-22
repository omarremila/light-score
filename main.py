from typing import Union, Optional
import random
import requests
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
import os
import logging
from datetime import datetime, timedelta
from fastapi import Request
import numpy as np
import geopandas as gpd
import math
import geopy.distance
import geopandas as gpd
import pandas as pd

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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


@app.get("/")
def read_root():
    return {"status": "healthy", "service": "light-score-api"}


def geocode_address(address: str) -> tuple[Optional[float], Optional[float]]:
    """Geocode an address using LocationIQ API."""
    api_key = os.getenv("LOCATIONIQ_API_KEY")
    if not api_key:
        logger.error("LocationIQ API key not found")
        return None, None

    try:
        base_url = "https://us1.locationiq.com/v1/search.php"
        params = {"key": api_key, "q": address, "format": "json", "limit": 1}

        logger.info(f"Geocoding address: {address}")
        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()
        if data and isinstance(data, list) and len(data) > 0:
            return float(data[0]["lat"]), float(data[0]["lon"])

        return None, None
    except Exception as e:
        logger.error(f"Geocoding error: {e}")
        return None, None


def buildings_nearby(
    path_to_shp, target_lat, target_long, min_height, direction, search_area=200
):
    # Read shapefile
    df = gpd.read_file(path_to_shp)
    threshold = search_area / 111111
    # Calculate differences vectorially
    df["lat_diff"] = df["LATITUDE"] - target_lat
    df["long_diff"] = df["LONGITUDE"] - target_long

    # Calculate distance vectorially
    df["avg_distance"] = np.sqrt(df["lat_diff"] ** 2 + df["long_diff"] ** 2)

    # Initial filtering using boolean masks
    mask = (
        (df["lat_diff"].abs() < threshold)
        & (df["long_diff"].abs() < threshold)
        & (df["AVG_HEIGHT"].astype(float) > min_height)
    )

    # Direction filtering
    if direction == "N":
        mask &= df["lat_diff"] > 0
    elif direction == "S":
        mask &= df["lat_diff"] < 0
    elif direction == "E":
        mask &= df["long_diff"] > 0
    elif direction == "W":
        mask &= df["long_diff"] < 0
    elif direction == "NE":
        mask &= (df["lat_diff"] > 0) & (df["long_diff"] > 0)
    elif direction == "NW":
        mask &= (df["lat_diff"] > 0) & (df["long_diff"] < 0)
    elif direction == "SE":
        mask &= (df["lat_diff"] < 0) & (df["long_diff"] > 0)
    elif direction == "SW":
        mask &= (df["lat_diff"] < 0) & (df["long_diff"] < 0)

    # Apply all filters at once
    filtered_df = df[mask].copy()

    result_df = filtered_df[
        [
            "LATITUDE",
            "LONGITUDE",
            "AVG_HEIGHT",
            "HEIGHT_MSL",
            "lat_diff",
            "long_diff",
            "avg_distance",
        ]
    ].rename(columns={"AVG_HEIGHT": "height", "HEIGHT_MSL": "elevation_above_c"})

    # Create target coordinates tuple
    target_coords = (float(target_lat), float(target_long))

    # Calculate accurate geodesic distance in meters for the sorted DataFrame
    result_df["distance_in_m"] = result_df.apply(
        lambda row: float(
            geopy.distance.geodesic(
                target_coords, (float(row["LATITUDE"]), float(row["LONGITUDE"]))
            ).km
            * 1000
        ),
        axis=1,
    )

    # Sort by avg_distance
    result_df = result_df.sort_values("distance_in_m")
    # Remove the first (users building) row
    result_df = result_df.iloc[1:].copy()
    return result_df


def calculate_base_score(
    primary_direction: str, buildings_df: gpd.GeoDataFrame, floor_num: int
) -> dict:
    """Calculate base light score based on buildings and direction."""
    try:
        if buildings_df.empty:
            return {
                "score": 95,
                "obstruction_details": "No significant obstructions found",
            }

        # Get closest building
        closest = buildings_df.iloc[0]
        distance = closest["distance"]
        height = closest["height"]

        # Calculate relative height considering floor
        relative_height = height - (floor_num * 3)  # Assuming 3m per floor

        # Calculate obstruction angle
        obstruction_angle = math.degrees(math.atan2(relative_height, distance))

        # Base score calculation considering direction
        if primary_direction == "S":
            if obstruction_angle < 15:
                base_score = 95
            elif obstruction_angle > 45:
                base_score = 40
            else:
                base_score = 95 - ((obstruction_angle - 15) * 1.8)  # Linear reduction
        else:
            if obstruction_angle < 20:
                base_score = 90
            elif obstruction_angle > 60:
                base_score = 50
            else:
                base_score = 90 - (
                    (obstruction_angle - 20) * 1
                )  # More lenient reduction

        return {
            "score": round(base_score, 1),
            "obstruction_angle": round(obstruction_angle, 1),
            "nearest_building_distance": round(distance),
            "nearest_building_height": round(height),
        }
    except Exception as e:
        logger.error(f"Error in base score calculation: {e}")
        return {"score": 70, "error": str(e)}


@app.get("/light_score/")
async def get_light_score(
    country: str,
    city: str,
    postalCode: str,
    streetName: str,
    streetNumber: str,
    floor: Union[str, None] = None,
    direction: Union[str, None] = None,
    startDate: Union[str, None] = None,
    endDate: Union[str, None] = None,
):
    """Calculate light score for an apartment."""
    try:
        # Validate required fields
        if not all([country, city, streetName, streetNumber]):
            raise HTTPException(status_code=400, detail="Missing required fields")

        # Validate direction if provided
        if direction and direction not in ["N", "S", "E", "W"]:
            raise HTTPException(
                status_code=400, detail="Direction must be one of: N, S, E, W"
            )

        # Set default dates if not provided
        if not startDate or not endDate:
            today = datetime.now()
            startDate = (today - timedelta(days=7)).strftime("%Y-%m-%d")
            endDate = today.strftime("%Y-%m-%d")

        # Get coordinates
        address = f"{streetNumber} {streetName}, {city}, {postalCode}, {country}"
        lat, lng = geocode_address(address)

        if not lat or not lng:
            raise HTTPException(
                status_code=404,
                detail="Could not find coordinates for the provided address",
            )

        # Initialize final score components
        floor_num = int(floor) if floor and floor.isdigit() else 1

        # Direction-based scoring
        direction_weights = {
            "S": 1.0,  # South gets full weight
            "E": 0.85,  # East slightly reduced
            "W": 0.85,  # West slightly reduced
            "N": 0.7,  # North most reduced
        }

        # Get buildings data
        try:
            buildings = buildings_nearby(
                "3D Massing (WGS84)/3DMassingShapefile_2023_WGS84.shp",
                lat,
                lng,
                50,  # min height
                direction or "S",  # Default to South if no direction specified
            )
        except Exception as e:
            logger.error(f"Error getting nearby buildings: {e}")
            buildings = gpd.GeoDataFrame()

        # Calculate base score
        score_details = calculate_base_score(direction or "S", buildings, floor_num)

        base_score = score_details["score"]

        # Apply direction weight
        if direction:
            base_score *= direction_weights.get(direction, 1.0)

        # Floor bonus (2% per floor, max 20%)
        floor_bonus = min(floor_num * 2, 20) if floor_num > 1 else 0

        # Calculate final score
        final_score = min(100, base_score + floor_bonus)

        return {
            "light_score": round(final_score, 1),
            "details": {
                "base_score": round(base_score, 1),
                "floor_bonus": floor_bonus,
                "direction": direction or "auto",
                "direction_factor": direction_weights.get(direction, 1.0),
                "obstruction_details": score_details,
                "floor_level": floor_num,
                "coordinates": {"lat": lat, "lng": lng},
            },
            "metadata": {
                "country": country,
                "city": city,
                "postalCode": postalCode,
                "streetName": streetName,
                "streetNumber": streetNumber,
                "startDate": startDate,
                "endDate": endDate,
            },
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(
            status_code=500, detail=f"An unexpected error occurred: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
