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

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Configure CORS - Simplified and corrected configuration
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
    """
    Geocode an address using LocationIQ API.
    """
    api_key = os.getenv("LOCATIONIQ_API_KEY")  # Updated environment variable name
    if not api_key:
        logger.error("LocationIQ API key not found in environment variables")
        return None, None

    try:
        base_url = "https://us1.locationiq.com/v1/search.php"
        params = {"key": api_key, "q": address, "format": "json", "limit": 1}

        logger.info(f"Geocoding address: {address}")
        response = requests.get(base_url, params=params, timeout=10)  # Added timeout
        response.raise_for_status()

        data = response.json()
        if data and isinstance(data, list) and len(data) > 0:
            return float(data[0]["lat"]), float(data[0]["lon"])

        logger.warning("No geocoding results found")
        return None, None

    except requests.exceptions.RequestException as e:
        logger.error(f"Geocoding API error: {e}")
        return None, None
    except (KeyError, ValueError, TypeError) as e:
        logger.error(f"Error parsing geocoding response: {e}")
        return None, None


def buildings_nearby(
    path_to_shp: str,
    target_lat: float,
    target_long: float,
    min_height: float,
    direction: str,
    search_area: float = 200,
) -> gpd.GeoDataFrame:
    """
    Find nearby buildings from a shapefile based on given criteria.
    """
    try:
        # Read shapefile
        df = gpd.read_file(path_to_shp)
        threshold = search_area / 111111

        # Calculate differences vectorially
        df["lat_diff"] = df["LATITUDE"].astype(float) - target_lat
        df["long_diff"] = df["LONGITUDE"].astype(float) - target_long

        # Calculate distance vectorially
        df["distance"] = np.sqrt(df["lat_diff"] ** 2 + df["long_diff"] ** 2)

        # Initial filtering using boolean masks
        mask = (
            (df["lat_diff"].abs() < threshold)
            & (df["long_diff"].abs() < threshold)
            & (df["AVG_HEIGHT"].astype(float) > min_height)
        )

        # Direction filtering
        direction_filters = {
            "N": df["lat_diff"] > 0,
            "S": df["lat_diff"] < 0,
            "E": df["long_diff"] > 0,
            "W": df["long_diff"] < 0,
            "NE": (df["lat_diff"] > 0) & (df["long_diff"] > 0),
            "NW": (df["lat_diff"] > 0) & (df["long_diff"] < 0),
            "SE": (df["lat_diff"] < 0) & (df["long_diff"] > 0),
            "SW": (df["lat_diff"] < 0) & (df["long_diff"] < 0),
        }

        if direction in direction_filters:
            mask &= direction_filters[direction]

        # Apply filters and process results
        filtered_df = df[mask].copy()
        result_df = filtered_df[
            ["LATITUDE", "LONGITUDE", "AVG_HEIGHT", "lat_diff", "long_diff", "distance"]
        ]
        result_df = result_df.rename(columns={"AVG_HEIGHT": "height"})

        # Process differences and sort
        result_df["lat_diff"] = result_df["lat_diff"].abs()
        result_df["long_diff"] = result_df["long_diff"].abs()

        return result_df.sort_values("distance")

    except Exception as e:
        logger.error(f"Error in buildings_nearby: {e}")
        return gpd.GeoDataFrame()


def calculate_sunlight_score(data: list) -> float:
    """
    Calculate the average sunlight score for the dataset.
    """
    try:
        # Extract valid sunlight data
        sunlight_data = [
            (day["sun_hours"], day["t_solar_rad"])
            for day in data
            if isinstance(day.get("sun_hours"), (int, float))
            and isinstance(day.get("t_solar_rad"), (int, float))
        ]

        if not sunlight_data:
            logger.error("No valid sunlight data found")
            return -1

        # Calculate ranges for normalization
        sun_hours_values, t_solar_rad_values = zip(*sunlight_data)
        sun_hours_range = max(sun_hours_values) - min(sun_hours_values)
        t_solar_rad_range = max(t_solar_rad_values) - min(t_solar_rad_values)

        # Normalize and calculate scores
        scores = []
        for sun_hours, t_solar_rad in sunlight_data:
            normalized_sun = (
                ((sun_hours - min(sun_hours_values)) / sun_hours_range * 100)
                if sun_hours_range
                else 0
            )
            normalized_rad = (
                ((t_solar_rad - min(t_solar_rad_values)) / t_solar_rad_range * 100)
                if t_solar_rad_range
                else 0
            )
            score = (0.6 * normalized_sun) + (0.4 * normalized_rad)
            scores.append(score)

        return round(sum(scores) / len(scores), 1) if scores else -1

    except Exception as e:
        logger.error(f"Error calculating sunlight score: {e}")
        return -1


def get_sunlight_data(lat: float, lon: float, startDate: str, endDate: str) -> float:
    """
    Get sunlight data from Weatherbit API.
    """
    api_key = os.getenv("WEATHERBIT_API_KEY")  # Updated environment variable name
    if not api_key:
        logger.error("Weatherbit API key not found in environment variables")
        return -1

    try:
        url = "https://api.weatherbit.io/v2.0/history/energy"
        params = {
            "lat": lat,
            "lon": lon,
            "start_date": startDate,  # Fixed parameter name
            "end_date": endDate,  # Fixed parameter name
            "key": api_key,
        }

        logger.info(f"Requesting weather data with params: {params}")
        response = requests.get(url, params=params, timeout=15)

        # Add more detailed logging
        if not response.ok:
            logger.error(
                f"Weatherbit API error: {response.status_code} - {response.text}"
            )
            return -1

        data = response.json()
        logger.info(f"Received data from Weatherbit: {data}")

        if not data.get("data"):
            logger.warning("No data received from Weatherbit")
            return -1

        return calculate_sunlight_score(data.get("data", []))

    except Exception as e:
        logger.error(f"Error in get_sunlight_data: {str(e)}")
        return -1


@app.get("/light_score/")
async def get_light_score(
    country: str,
    city: str,
    postalCode: str,  # Changed from postalCode
    streetName: str,  # Changed from streetName
    streetNumber: str,  # Changed from streetNumber
    floor: Union[str, None] = None,
    startDate: Union[str, None] = None,  # Changed from startDate
    endDate: Union[str, None] = None,  # Changed from endDate
):
    """Calculate light score for a given address and date range."""
    try:
        # Validate required fields
        if not all([country, city, streetName, streetNumber]):
            raise HTTPException(
                status_code=400,
                detail="Missing required fields: country, city, streetName, and streetNumber are required",
            )

        # Set default dates if not provided
        if not startDate or not endDate:
            today = datetime.now()
            startDate = (today - timedelta(days=7)).strftime("%Y-%m-%d")
            endDate = today.strftime("%Y-%m-%d")

        # Format address and get coordinates
        address = f"{streetNumber} {streetName}, {city}, {postalCode}, {country}"
        lat, lng = geocode_address(address)

        if not lat or not lng:
            raise HTTPException(
                status_code=404,
                detail="Could not find coordinates for the provided address",
            )

        # Get light score
        light_score = get_sunlight_data(lat, lng, startDate, endDate)
        if light_score == -1:
            raise HTTPException(
                status_code=500, detail="Could not retrieve or calculate sunlight data"
            )

        # Apply floor adjustment
        if floor and floor.isdigit():
            floor_num = int(floor)
            if floor_num > 1:
                adjustment = min(floor_num * 2, 20)  # 2% per floor, max 20%
                light_score = min(100, light_score + adjustment)

        return {
            "country": country,
            "city": city,
            "postalCode": postalCode,
            "streetName": streetName,
            "streetNumber": streetNumber,
            "floor": floor,
            "light_score": light_score,
            "lat": lat,
            "lng": lng,
            "startDate": startDate,
            "endDate": endDate,
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Unexpected error in light score calculation: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred while calculating the light score: {str(e)}",
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
