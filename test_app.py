from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import math  # Add this import!

app = FastAPI()


# Error handler for unexpected errors
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return {"error": str(exc)}, 500


# Configure CORS for local testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dummy data for testing
DUMMY_BUILDINGS = {
    "downtown": {
        "N": {"height": 150, "distance": 50},
        "S": {"height": 200, "distance": 75},
        "E": {"height": 175, "distance": 60},
        "W": {"height": 125, "distance": 45},
    },
    "suburban": {
        "N": {"height": 50, "distance": 100},
        "S": {"height": 75, "distance": 150},
        "E": {"height": 60, "distance": 120},
        "W": {"height": 45, "distance": 90},
    },
}


def geocode_address(address: str):
    # Dummy geocoding that returns test coordinates
    if "downtown" in address.lower():
        return 43.6532, -79.3832  # Downtown Toronto coordinates
    return 43.7615, -79.4111  # Suburban coordinates


def get_building_data(lat: float, lng: float, direction: str):
    # Return dummy building data based on approximate location
    if lat < 43.7:  # Downtown
        return DUMMY_BUILDINGS["downtown"][direction]
    return DUMMY_BUILDINGS["suburban"][direction]


def calculate_light_score(building_data: dict, floor: int, direction: str):
    if not building_data:
        return {"score": 95, "reason": "No buildings found"}

    relative_height = building_data["height"] - (floor * 3)
    angle = math.degrees(math.atan2(relative_height, building_data["distance"]))

    if direction == "S":
        score = 95 - (angle / 2)  # Simplified calculation
    else:
        score = 90 - (angle / 2)

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
