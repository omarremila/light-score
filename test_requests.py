import requests


def test_light_score():
    # Test case for 19 Grand Trunk Crescent
    address = {
        "country": "Canada",
        "city": "Toronto",
        "postalCode": "M5J 3A3",
        "streetName": "Grand Trunk Crescent",
        "streetNumber": "19",
        "floor": 5,  # You can change this
        "direction": "S",  # Test different directions: N, S, E, W
    }

    try:
        response = requests.get("http://localhost:8000/light_score/", params=address)
        print(f"\nTesting address: {address['streetNumber']} {address['streetName']}")
        print(f"Status code: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print("\nDetailed Response:")
            print(f"Light Score: {data.get('light_score')}")
            print(f"Coordinates: {data.get('coordinates')}")
            print("\nDetails:")
            for key, value in data.get("details", {}).items():
                print(f"{key}: {value}")
            print("\nBuilding Data:")
            print(data.get("building_data"))
        else:
            print("Error:", response.text)

    except requests.exceptions.ConnectionError:
        print("Error: Cannot connect to server. Is it running?")
    except Exception as e:
        print(f"Error: {str(e)}")


# Test different floors and directions
def test_multiple_scenarios():
    floors = [1, 5, 10, 20, 30]
    directions = ["N", "S", "E", "W"]

    for floor in floors:
        for direction in directions:
            print(f"\n=== Testing Floor {floor}, Direction {direction} ===")
            test_light_score(floor=floor, direction=direction)


if __name__ == "__main__":
    test_light_score()
    # Uncomment below to test multiple scenarios
    # test_multiple_scenarios()
