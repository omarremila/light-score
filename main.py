from typing import Union
import random

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
origins = [
    "http://localhost:5173",  # Add other origins as needed
]
import requests



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
    api_key = 'YOUR_API_KEY'
    base_url = "https://maps.googleapis.com/maps/api/geocode/json"
    endpoint = f"{base_url}?address={address}&key={api_key}"
    response = requests.get(endpoint)
    if response.status_code == 200:
        results = response.json()['results']
        if results:
            location = results[0]['geometry']['location']
            return location['lat'], location['lng']
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
    # Generate a random score between 0 and 100
    light_score = random.randint(0, 100)
    return {
        "country": country,
        "city": city,
        "postal_code": postal_code,
        "street_number": street_number,
        "floor": floor,
        "light_score": light_score,
     
    }