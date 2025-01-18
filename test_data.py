# test_gis.py
import geopandas as gpd
import fiona
import shapely
import os


def test_shapefile():
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        shapefile_path = os.path.join(
            base_dir, "data", "3DMassingShapefile_2023_WGS84.shp"
        )

        print(f"Testing file at: {shapefile_path}")
        print(f"File exists: {os.path.exists(shapefile_path)}")

        gdf = gpd.read_file(shapefile_path)
        print("\nSuccess! Found the following columns:")
        print(gdf.columns.tolist())
        print(f"\nTotal number of buildings: {len(gdf)}")

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_shapefile()
