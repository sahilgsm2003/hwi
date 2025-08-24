import os
import rasterio
import numpy as np
from datetime import datetime
import requests
from geopy.geocoders import Nominatim
from collections import defaultdict
from datetime import timedelta

# --- 1. CONFIGURATION ---
CLIENT_ID = "sh-61654116-66e8-45f4-a553-50ad0a07929a"
CLIENT_SECRET = "Tusibl8GSpjCDDWJOgO85GINHTv93GAG"
BASE_DATA_DIR = "data"

# This is no longer a fixed window, but will be determined dynamically.
# SEASONAL_WINDOW = ("06-01", "08-31") 

NDVI_EVALSCRIPT = """
//VERSION=3
function setup() {
    return {
        input: [{
            bands: ["B04", "B08", "SCL", "dataMask"]
        }],
        output: {
            bands: 1,
            sampleType: "FLOAT32"
        }
    };
}
function evaluatePixel(sample) {
    let ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04);
    if (sample.SCL == 3 || sample.SCL == 8 || sample.SCL == 9 || sample.SCL == 10 || sample.SCL == 11) {
        return [NaN]; // Cloud, cloud shadow, or snow
    }
    return [ndvi];
}
"""

# --- 2. AUTHENTICATION & GECODING ---
def get_access_token():
    auth_url = 'https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token'
    auth_data = {'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'grant_type': 'client_credentials'}
    try:
        response = requests.post(auth_url, data=auth_data)
        response.raise_for_status()
        return response.json()['access_token']
    except requests.exceptions.RequestException as e:
        print(f"Error during authentication: {e}")
        return None

def get_coords_from_place_name(place_name):
    """Converts a place name to latitude and longitude."""
    try:
        geolocator = Nominatim(user_agent="vegetation_analyzer")
        location = geolocator.geocode(place_name)
        if location:
            return True, (location.latitude, location.longitude)
        else:
            return False, "Location not found."
    except Exception as e:
        return False, str(e)

# --- 3. DATA DOWNLOADING & PROCESSING ---
def find_optimal_seasonal_window(token, bbox):
    """
    Analyzes 5 years of metadata to find the 3-month window with the
    lowest average cloud cover.
    """
    print("--- Analyzing historical data to find clearest season ---")
    monthly_cloud_cover = defaultdict(list)
    today = datetime.now()

    # 1. Fetch metadata for the last 5 years
    for i in range(5):
        end_date = today - timedelta(days=i * 365)
        start_date = end_date - timedelta(days=365)
        search_url = "https://sh.dataspace.copernicus.eu/api/v1/catalog/1.0.0/search"
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        search_payload = {
            "bbox": bbox, "datetime": f"{start_date.strftime('%Y-%m-%d')}T00:00:00Z/{end_date.strftime('%Y-%m-%d')}T23:59:59Z",
            "collections": ["sentinel-2-l2a"], "limit": 100
        }
        try:
            response = requests.post(search_url, headers=headers, json=search_payload, timeout=60)
            response.raise_for_status()
            features = response.json().get('features', [])
            for f in features:
                month = datetime.strptime(f['properties']['datetime'][:10], '%Y-%m-%d').month
                cloud_cover = f['properties'].get('eo:cloud_cover', 100)
                monthly_cloud_cover[month].append(cloud_cover)
        except requests.exceptions.RequestException:
            continue # If one year fails, just continue

    # 2. Calculate average cloud cover for each month
    avg_monthly_cc = {}
    for month, values in monthly_cloud_cover.items():
        avg_monthly_cc[month] = np.mean(values) if values else 100

    if len(avg_monthly_cc) < 3:
        print("  ! Not enough historical data. Defaulting to Oct-Dec window.")
        return (10, 12)

    # 3. Find the 3-month window with the lowest sum of averages
    min_cc = float('inf')
    best_start_month = -1
    # Check all possible 3-month windows, including wrapping around the year
    for i in range(1, 13):
        month1 = i
        month2 = (i % 12) + 1
        month3 = ((i + 1) % 12) + 1
        
        cc1 = avg_monthly_cc.get(month1, 100)
        cc2 = avg_monthly_cc.get(month2, 100)
        cc3 = avg_monthly_cc.get(month3, 100)
        current_cc = cc1 + cc2 + cc3

        if current_cc < min_cc:
            min_cc = current_cc
            best_start_month = month1
    
    # Convert start month to a (start_month, end_month) tuple
    start_month = best_start_month
    end_month = ((best_start_month + 1) % 12) + 1
    
    print(f"  ✓ Optimal window found: Month {start_month} to {end_month}")
    return (start_month, end_month)

def download_and_composite_for_year(token, bbox, year, seasonal_window, location_data_dir):
    """
    Finds the best 10 images for a given year's optimal seasonal window,
    downloads them, and creates a single max composite TIFF.
    """
    start_month, end_month = seasonal_window
    
    # Handle year wrapping for the date range
    if start_month <= end_month:
        start_date = datetime(year, start_month, 1)
        end_date = datetime(year, end_month, 1) + timedelta(days=31) # Go to start of next month
        end_date = min(datetime(year, end_month, 31), end_date - timedelta(days=end_date.day)) # get last day of month
    else: # Window wraps around new year, e.g., Nov-Jan
        start_date = datetime(year - 1, start_month, 1)
        end_date = datetime(year, end_month, 31)

    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")
    
    print(f"\n--- Processing Year {year} (Optimal Window: {start_date_str} to {end_date_str}) ---")

    # 1. Search for available scenes
    search_url = "https://sh.dataspace.copernicus.eu/api/v1/catalog/1.0.0/search"
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    search_payload = {
        "bbox": bbox, "datetime": f"{start_date_str}T00:00:00Z/{end_date_str}T23:59:59Z",
        "collections": ["sentinel-2-l2a"], "limit": 50
    }
    
    try:
        response = requests.post(search_url, headers=headers, json=search_payload)
        response.raise_for_status()
        features = response.json().get('features', [])
    except requests.exceptions.RequestException as e:
        print(f"  ✗ Could not search for scenes in {year}: {e}")
        return None # Skip this year

    if not features:
        print(f"  ✗ No scenes found for {year}.")
        return None

    # 2. Sort locally and select the best ones
    features.sort(key=lambda f: f['properties'].get('eo:cloud_cover', 101))
    best_features = features[:15] # Increase to 15 for better coverage
    print(f"  ✓ Found {len(features)} scenes, selecting top {len(best_features)} to create composite.")

    # 3. Download the selected images
    image_paths_for_composite = []
    for feature in best_features:
        date = feature['properties']['datetime'][:10]
        cloud_cover = feature['properties'].get('eo:cloud_cover', -1)
        filename = f"{year}_{date}_cc{cloud_cover:.2f}.tiff"
        filepath = os.path.join(location_data_dir, filename)
        
        if not os.path.exists(filepath):
            print(f"    Downloading {filename}...")
            download_single_image(token, bbox, date, filepath, NDVI_EVALSCRIPT)
        
        if os.path.exists(filepath):
             image_paths_for_composite.append(filepath)

    if not image_paths_for_composite:
        print(f"  ✗ Failed to download any images for {year}.")
        return None

    # 4. Create and save the composite image
    output_filename = f"composite_max_{year}_{bbox[1]}_{bbox[0]}.tiff"
    output_path = os.path.join("output", output_filename)
    create_composite_image(image_paths_for_composite, output_path, method='max')
    
    return output_path


def download_single_image(token, bbox, date, filepath, evalscript):
    process_url = "https://sh.dataspace.copernicus.eu/api/v1/process"
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json', 'Accept': 'image/tiff'}
    payload = {
        "input": { "bounds": {"bbox": bbox, "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}}, "data": [{"type": "sentinel-2-l2a", "dataFilter": {"timeRange": {"from": f"{date}T00:00:00Z", "to": f"{date}T23:59:59Z"}}}]},
        "output": {"width": 512, "height": 512, "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}]},
        "evalscript": evalscript
    }
    try:
        response = requests.post(process_url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        with open(filepath, 'wb') as f: f.write(response.content)
    except requests.exceptions.RequestException as e:
        print(f"    ✗ Download error for {date}: {e}")

def create_composite_image(image_paths, output_path, method='max'):
    if not image_paths:
        raise ValueError("Image path list is empty for compositing.")

    _, profile = read_tiff(image_paths[0])
    image_stack = [read_tiff(path)[0] for path in image_paths]
    stack_3d = np.stack(image_stack, axis=0)

    if method == 'max':
        composite_data = np.nanmax(stack_3d, axis=0)
    else: # mean
        composite_data = np.nanmean(stack_3d, axis=0)

    profile.update(dtype=rasterio.float32, count=1, nodata=np.nan)
    with rasterio.open(output_path, 'w', **profile) as dst:
        dst.write(composite_data.astype(rasterio.float32), 1)
    print(f"  ✓ Composite image saved to: {output_path}")

def read_tiff(file_path):
    with rasterio.open(file_path) as src:
        data = src.read(1).astype('float32')
        nodata = src.nodata
        if nodata is not None:
            data[data == nodata] = np.nan
        return data, src.profile
        
# --- 4. MAIN CONTROLLER ---
def generate_yearly_composites(bbox, start_year, end_year):
    """
    Main controller. Determines optimal season then generates yearly composites.
    """
    try:
        bbox_str = "_".join(map(str, bbox))
        location_data_dir = os.path.join(BASE_DATA_DIR, bbox_str)
        os.makedirs(location_data_dir, exist_ok=True)
        
        token = get_access_token()
        if not token:
            return False, "Failed to authenticate with Copernicus."

        # Find the best seasonal window first
        optimal_window = find_optimal_seasonal_window(token, bbox)

        results = {"composites": {}, "skipped_years": [], "optimal_window_months": optimal_window}
        for year in range(start_year, end_year + 1):
            composite_path = download_and_composite_for_year(
                token, bbox, year, optimal_window, location_data_dir
            )
            if composite_path:
                results["composites"][year] = composite_path
            else:
                results["skipped_years"].append(year)
        
        return True, results

    except Exception as e:
        print(f"An unexpected error occurred in generate_yearly_composites: {e}")
        return False, str(e)
