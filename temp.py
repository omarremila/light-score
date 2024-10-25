import sys
import json
print("Python version:", sys.version)

import requests
def get_solcast_data(lat, lon):
    api_key = 'REMOVED_API_KEY'
    endpoint = f"https://api.solcast.com.au/radiation/forecasts?latitude={lat}&longitude={lon}&apiid={api_key}&tab=json"
    print(endpoint)
    
    response = requests.get(endpoint)
    response.raise_for_status()  # raises exception when not a 2xx response
    print("Request URL:", endpoint)
    
    response = requests.get(endpoint)
    
    print("Response status code:", response.status_code)
    print("Response text:", response.text)  # Print the raw response content for debugging
    if response.status_code != 204:
        return response.json()
    return None

# Example usage
lat, lon = 43.651070, -79.347015  # Coordinates for Toronto
data = get_solcast_data(lat, lon)
if data:
    print(data)

