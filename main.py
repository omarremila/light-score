from typing import Union
import random
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
# Configure CORS
origins = [
    "http://localhost:5173",  # Your frontend URL
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
    api_key = 'API KEY'
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

# Function to get sunlight data (using a placeholder API or dataset for solar radiation)
def get_sunlight_data(lat, lng):
    # Placeholder for actual sunlight data API
    return random.uniform(0, 100)  # Replace with actual API call

# Function to account for nearby building obstructions
def get_obstruction_factor(lat, lng):
    # Placeholder for actual building data API
    return random.uniform(0, 1)  # 0 means no obstruction, 1 means full obstruction

@app.get("/light_score/")
def get_light_score(
    country: str,
    city: str,
    postal_code: str,
    street_number: str,
    floor: Union[str, None] = None
):
    address = f"{street_number}, {city}, {postal_code}, {country}"
    lat, lng = geocode_address(address)  # Get latitude and longitude
    # Generate a random score between 0 and 100
    light_score = random.randint(0, 100)
    # Return lat, lng, and light score in the response
    return {
        "country": country,
        "city": city,
        "postal_code": postal_code,
        "street_number": street_number,
        "floor": floor,
        "light_score": light_score,
        "lat": lat,
        "lng": lng,
    }