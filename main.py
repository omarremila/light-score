from typing import Union
import random
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

def calculate_sunlight_score(data):
    """
    Calculate the average sunlight score for the entire dataset.

    :param data: List of dictionaries containing `sun_hours` and `t_solar_rad` for each day.
    :return: The average sunlight score, rounded to one decimal place.
    """
    # Step 1: Extract relevant data
    sunlight_data = [(day['sun_hours'], day['t_solar_rad']) for day in data if 'sun_hours' in day and 't_solar_rad' in day]

    # Step 2: Find min and max for each metric to normalize
    min_sun_hours = min(sun_hours for sun_hours, _ in sunlight_data)
    max_sun_hours = max(sun_hours for sun_hours, _ in sunlight_data)
    min_t_solar_rad = min(t_solar_rad for _, t_solar_rad in sunlight_data)
    max_t_solar_rad = max(t_solar_rad for _, t_solar_rad in sunlight_data)

    # Normalize values and calculate the weighted score (60% `sun_hours`, 40% `t_solar_rad`)
    def normalize(sun_hours, t_solar_rad):
        normalized_sun_hours = ((sun_hours - min_sun_hours) / (max_sun_hours - min_sun_hours) * 100) if max_sun_hours != min_sun_hours else 0
        normalized_t_solar_rad = ((t_solar_rad - min_t_solar_rad) / (max_t_solar_rad - min_t_solar_rad) * 100) if max_t_solar_rad != min_t_solar_rad else 0
        return (0.6 * normalized_sun_hours) + (0.4 * normalized_t_solar_rad)

    # Step 3: Calculate sunlight score for each day
    sunlight_scores = [normalize(sun_hours, t_solar_rad) for sun_hours, t_solar_rad in sunlight_data]

    # Step 4: Calculate the average sunlight score and round to one decimal place
    average_sunlight_score = sum(sunlight_scores) / len(sunlight_scores) if sunlight_scores else 0
    return round(average_sunlight_score, 1)

app = FastAPI()
# Configure CORS
origins = [
    "https://ligh-score-production.up.railway.app/light-score",  
    "https://light-score-production.up.railway.app"  #  Railway backend URL

]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/items/{item_id}")
def read_item(item_id: int, q: Union[str, None] = None):
    return {"item_id": item_id, "q": q}

def geocode_address(address):
    api_key = os.getenv('api_key')
    base_url = f"https://us1.locationiq.com/v1/search.php?key={api_key}"
    params = {
        'q': address,
        'format': 'json',
        'limit': 1
    }
    response = requests.get(base_url, params=params)
    if response.status_code == 200:
        data = response.json()
        if data:
            return data[0]['lat'], data[0]['lon']
    return None, None

weatherbit_api_key = os.getenv('weatherbit_api_key')

def get_sunlight_data(lat, lon,start_date,end_date):
    url = f"https://api.weatherbit.io/v2.0/history/energy?lat={lat}&lon={lon}&start_date={start_date}&end_date={end_date}&key={weatherbit_api_key}"
    print (url)
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json().get("data", [])
        # Extract and calculate average solar radiation (using 'ghi' for Global Horizontal Irradiance)
        #total_solar_rad = sum(day.get("ghi", 0) for day in data if day.get("ghi") is not None)
        #avg_solar_rad = total_solar_rad / len(data) if data else 0
        light_score = calculate_sunlight_score(data)
        print (light_score)
        return light_score
    return -1

# Function to account for nearby building obstructions
def get_obstruction_factor(lat, lng):
    # Placeholder for actual building data API
    return random.uniform(0, 1)  # 0 means no obstruction, 1 means full obstruction

@app.get("/light_score/")
@app.get("/light_score/")
def get_light_score(
    country: str,
    city: str,
    postal_code: str,
    street_name: str,
    street_number: str,
    floor: Union[str, None] = None,
    start_date: Union[str, None] = None,
    end_date: Union[str, None] = None
):
    # Use a default date range if not provided
    if not start_date or not end_date:
        start_date = "2023-06-21"  # Example default
        end_date = "2023-06-21"    # Example default

    # Get lat and lon based on address
    address = f"{street_number}, {city}, {postal_code}, {country}"
    lat, lng = geocode_address(address)

    # Calculate sunlight strength over date range
    light_score = get_sunlight_data(lat, lng, start_date, end_date) if lat and lng else None

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
        "end_date": end_date,
    }
