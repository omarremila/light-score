from typing import Union
import random
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import logging
from typing import Optional
from datetime import datetime, timedelta
from fastapi import Request

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Configure CORS
origins = [
    "https://sun-light-strength.up.railway.app/",
    "http://localhost:5173"  # Local development
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def cors_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["Access-Control-Allow-Origin"] = "https://sun-light-strength.up.railway.app/"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response
# Add OPTIONS endpoint to handle preflight requests
@app.options("/{path:path}")
async def options_handler(request: Request, path: str):
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "https://sun-light-strength.up.railway.app/",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Credentials": "true",
        }
    )
@app.get("/")
def read_root():
    return {"status": "healthy", "service": "light-score-api"}
def geocode_address(address: str) -> tuple[Optional[float], Optional[float]]:
    """
    Geocode an address using LocationIQ API.
    
    :param address: The address to geocode
    :return: Tuple of (latitude, longitude) or (None, None) if geocoding fails
    """
    api_key = os.getenv('api_key')
    if not api_key:
        logger.error("LocationIQ API key not found in environment variables")
        return None, None

    try:
        base_url = "https://us1.locationiq.com/v1/search.php"
        params = {
            'key': api_key,
            'q': address,
            'format': 'json',
            'limit': 1
        }
        
        logger.info(f"Geocoding address: {address}")
        response = requests.get(base_url, params=params)
        response.raise_for_status()

        data = response.json()
        if data and isinstance(data, list) and len(data) > 0:
            return float(data[0]['lat']), float(data[0]['lon'])
        
        logger.warning("No geocoding results found")
        return None, None

    except requests.exceptions.RequestException as e:
        logger.error(f"Geocoding API error: {e}")
        return None, None
    except (KeyError, ValueError, TypeError) as e:
        logger.error(f"Error parsing geocoding response: {e}")
        return None, None



def buildings_nearby(path_to_shp, target_lat, target_long, min_height, direction, search_area=200):
    # Read shapefile
    df = gpd.read_file(path_to_shp)
    threshold = search_area / 111111
    # Calculate differences vectorially
    df['lat_diff'] = df['LATITUDE'] - target_lat
    df['long_diff'] = df['LONGITUDE'] - target_long
    
    # Calculate distance vectorially
    df['distance'] = np.sqrt(df['lat_diff']**2 + df['long_diff']**2)
    
    # Initial filtering using boolean masks
    mask = (
        (df['lat_diff'].abs() < threshold) & 
        (df['long_diff'].abs() < threshold) & 
        (df['AVG_HEIGHT'].astype(float) > min_height)
    )
    
    # Direction filtering
    if direction == 'N':
        mask &= (df['lat_diff'] > 0)
    elif direction == 'S':
        mask &= (df['lat_diff'] < 0)
    elif direction == 'E':
        mask &= (df['long_diff'] > 0)
    elif direction == 'W':
        mask &= (df['long_diff'] < 0)
    elif direction == 'NE':
        mask &= (df['lat_diff'] > 0) & (df['long_diff'] > 0)
    elif direction == 'NW':
        mask &= (df['lat_diff'] > 0) & (df['long_diff'] < 0)
    elif direction == 'SE':
        mask &= (df['lat_diff'] < 0) & (df['long_diff'] > 0)
    elif direction == 'SW':
        mask &= (df['lat_diff'] < 0) & (df['long_diff'] < 0)
    
    # Apply all filters at once
    filtered_df = df[mask].copy()
    
    # Select and rename columns
    result_df = filtered_df[[
        'LATITUDE', 'LONGITUDE', 'AVG_HEIGHT', 
        'lat_diff', 'long_diff', 'distance'
    ]].rename(columns={
        'AVG_HEIGHT': 'height'
    })
    
    # Take absolute values of differences
    result_df['lat_diff'] = result_df['lat_diff'].abs()
    result_df['long_diff'] = result_df['long_diff'].abs()
    
    # Sort by distance
    return result_df.sort_values('distance')


def calculate_sunlight_score(data):
    """
    Calculate the average sunlight score for the entire dataset.
    
    :param data: List of dictionaries containing `sun_hours` and `t_solar_rad` for each day.
    :return: The average sunlight score, rounded to one decimal place.
    """
    try:
        # Step 1: Extract relevant data
        sunlight_data = [(day['sun_hours'], day['t_solar_rad']) 
                        for day in data 
                        if 'sun_hours' in day and 't_solar_rad' in day]

        if not sunlight_data:
            logger.error("No valid sunlight data found")
            return -1

        # Step 2: Find min and max for each metric to normalize
        min_sun_hours = min(sun_hours for sun_hours, _ in sunlight_data)
        max_sun_hours = max(sun_hours for sun_hours, _ in sunlight_data)
        min_t_solar_rad = min(t_solar_rad for _, t_solar_rad in sunlight_data)
        max_t_solar_rad = max(t_solar_rad for _, t_solar_rad in sunlight_data)

        # Normalize values and calculate weighted score
        def normalize(sun_hours, t_solar_rad):
            normalized_sun_hours = (
                ((sun_hours - min_sun_hours) / (max_sun_hours - min_sun_hours) * 100) 
                if max_sun_hours != min_sun_hours else 0
            )
            normalized_t_solar_rad = (
                ((t_solar_rad - min_t_solar_rad) / (max_t_solar_rad - min_t_solar_rad) * 100) 
                if max_t_solar_rad != min_t_solar_rad else 0
            )
            return (0.6 * normalized_sun_hours) + (0.4 * normalized_t_solar_rad)

        # Calculate scores and average
        sunlight_scores = [normalize(sun_hours, t_solar_rad) 
                         for sun_hours, t_solar_rad in sunlight_data]
        
        average_sunlight_score = sum(sunlight_scores) / len(sunlight_scores) if sunlight_scores else 0
        return round(average_sunlight_score, 1)

    except Exception as e:
        logger.error(f"Error calculating sunlight score: {e}")
        return -1


def get_sunlight_data(lat: float, lon: float, start_date: str, end_date: str) -> float:
    """
    Get sunlight data from Weatherbit API.
    
    :param lat: Latitude
    :param lon: Longitude
    :param start_date: Start date in YYYY-MM-DD format
    :param end_date: End date in YYYY-MM-DD format
    :return: Light score or -1 if error
    """
    weatherbit_api_key = os.getenv('weatherbit_api_key')
    if not weatherbit_api_key:
        logger.error("Weatherbit API key not found in environment variables")
        return -1

    try:
        url = f"https://api.weatherbit.io/v2.0/history/energy"
        params = {
            'lat': lat,
            'lon': lon,
            'start_date': start_date,
            'end_date': end_date,
            'key': weatherbit_api_key
        }
        
        logger.info(f"Requesting weather data for coordinates: {lat}, {lon}")
        response = requests.get(url, params=params)
        response.raise_for_status()

        data = response.json().get("data", [])
        if not data:
            logger.warning("No weather data received")
            return -1

        light_score = calculate_sunlight_score(data)
        logger.info(f"Calculated light score: {light_score}")
        return light_score

    except requests.exceptions.RequestException as e:
        logger.error(f"Weather API error: {e}")
        return -1
    except Exception as e:
        logger.error(f"Error processing weather data: {e}")
        return -1



@app.get("/light_score/")
async def get_light_score(
    country: str,
    city: str,
    postal_code: str,
    street_name: str,
    street_number: str,
    floor: Union[str, None] = None,
    start_date: Union[str, None] = None,
    end_date: Union[str, None] = None
):
    """Calculate light score for a given address and date range."""
    # Validate required fields
    if not all([country, city, street_name, street_number]):
        raise HTTPException(
            status_code=400,
            detail="Missing required fields: country, city, street_name, and street_number are required"
        )

    # Set default dates if not provided
    if not start_date or not end_date:
        today = datetime.now()
        start_date = (today - timedelta(days=7)).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')

    try:
        # Format address and get coordinates
        address = f"{street_number} {street_name}, {city}, {postal_code}, {country}"
        lat, lng = geocode_address(address)
        
        if not lat or not lng:
            raise HTTPException(
                status_code=404,
                detail="Could not find coordinates for the provided address"
            )

        # Get light score
        light_score = get_sunlight_data(lat, lng, start_date, end_date)
        if light_score == -1:
            raise HTTPException(
                status_code=500,
                detail="Could not retrieve or calculate sunlight data"
            )

        # Apply floor adjustment if provided
        if floor and floor.isdigit():
            floor_num = int(floor)
            if floor_num > 1:
                # Simple adjustment: increase score by 2% per floor, max 20%
                adjustment = min(floor_num * 2, 20)
                light_score = min(100, light_score + adjustment)

        # Return the result
        return {
            "country": country,
            "city": city,
            "postal_code": postal_code,
            "street_name": street_name,
            "street_number": street_number,
            "floor": floor,
            "light_score": light_score,
            "lat": lat,
            "lng": lng,
            "start_date": start_date,
            "end_date": end_date
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in light score calculation: {e}")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while calculating the light score"
        )
