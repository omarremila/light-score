The application requires the following environment variables:

- `LOCATIONIQ_API_KEY`: API key for LocationIQ geocoding service

## Running the Application

Start the FastAPI server:

```bash
uvicorn main:app --reload
```

The server will start on `http://localhost:8000`

## API Endpoints

### GET /light_score/

Calculates a light score for a given address.

#### Request Parameters

- `country` (string): Country name
- `city` (string): City name
- `postalCode` (string): Postal/ZIP code
- `streetName` (string): Street name
- `streetNumber` (string): Street number
- `floor` (integer, optional): Floor number (default: 1)
- `direction` (string, optional): Window direction (default: "S")
  - Valid values: "N", "S", "E", "W", "NE", "NW", "SE", "SW"

#### Response Format

```javascript
{
    "coordinates": {
        "lat": float,  // Latitude of the address
        "lng": float   // Longitude of the address
    },
    "light_score": float,  // Final calculated light score (0-100)
    "details": {
        "base_score": float,  // Initial score before adjustments
        "floor_bonus": float, // Bonus points based on floor number
        "direction": string,  // Window direction
        "sun_blockage": {
            "is_blocked": boolean,
            "blockage_percentage": float,
            "blocking_buildings": [
                {
                    "distance": float,    // Distance to blocking building (meters)
                    "height": float,      // Height of blocking building (meters)
                    "angle": float,       // Angular height of building (degrees)
                    "azimuth_diff": float, // Difference in azimuth from sun (degrees)
                    "impact": float       // Impact on blockage calculation
                }
            ]
        },
        "obstruction_factor": float  // General obstruction factor (0-1)
    },
    "sun_position": {
        "elevation": float,  // Sun's elevation angle (degrees)
        "azimuth": float    // Sun's azimuth angle (degrees)
    },
    "building_data": [
        {
            "distance": float,    // Distance to nearby building (meters)
            "height_max": float,  // Maximum height of building (meters)
            "height": float,      // Height above mean sea level (meters)
            "area": float,        // Building's area (square meters)
            "lat": float,        // Building's latitude
            "lng": float         // Building's longitude
        }
    ]
}
```

## Testing

The repository includes test files for both the API and data processing:

- `test_app.py`: API endpoint testing
- `test_data.py`: Building data processing testing
- `test_requests.py`: Sample API requests

Run tests using:

```bash
python -m pytest
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.
