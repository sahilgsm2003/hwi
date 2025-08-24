import os
import rasterio
import numpy as np
from datetime import datetime, timedelta
import requests

# --- 1. CONFIGURATION ---
CLIENT_ID = "sh-61654116-66e8-45f4-a553-50ad0a07929a"
CLIENT_SECRET = "Tusibl8GSpjCDDWJOgO85GINHTv93GAG"
BASE_DATA_DIR = "data"

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

# --- 2. AUTHENTICATION ---
def get_access_token():
    auth_url = 'https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token'
    auth_data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'client_credentials'
    }
    try:
        response = requests.post(auth_url, data=auth_data)
        response.raise_for_status()
        return response.json()['access_token']
    except requests.exceptions.RequestException as e:
        print(f"Error during authentication: {e}")
        return None

# --- 3. DATA DOWNLOADING ---
def get_best_images_for_bbox(token, bbox, download_dir):
    """
    Finds and downloads the 2 best (lowest cloud cover) images for each of the past 5 years.
    """
    all_features = []
    today = datetime.now()

    for i in range(5):
        end_date = today - timedelta(days=i * 365)
        start_date = end_date - timedelta(days=365)
        
        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")
        
        print(f"\nSearching for images between {start_date_str} and {end_date_str}...")
        
        search_url = "https://sh.dataspace.copernicus.eu/api/v1/catalog/1.0.0/search"
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        
        # Search payload without server-side sorting. We will sort locally.
        search_payload = {
            "bbox": bbox,
            "datetime": f"{start_date_str}T00:00:00Z/{end_date_str}T23:59:59Z",
            "collections": ["sentinel-2-l2a"],
            "limit": 50 # Fetch up to 50 scenes to ensure we get some good ones
        }
        
        try:
            response = requests.post(search_url, headers=headers, json=search_payload)
            response.raise_for_status()
            features = response.json().get('features', [])
            
            # --- Sort the results locally by cloud cover ---
            features.sort(key=lambda f: f['properties'].get('eo:cloud_cover', 101)) # Sort by cloud cover, default to 101 if not present
            
            # Take the top 2 features for the year
            top_features = features[:2]
            print(f"Found {len(features)} scenes, selecting top {len(top_features)} for the year by cloud cover.")
            all_features.extend(top_features)
        except requests.exceptions.RequestException as e:
            print(f"Could not search for year {i+1}: {e}")
            continue

    if not all_features:
        return False

    print(f"\nFound a total of {len(all_features)} candidate images over 5 years. Downloading them...")
    for feature in all_features:
        date = feature['properties']['datetime'][:10]
        cloud_cover = feature['properties']['eo:cloud_cover']
        filename = f"ndvi_{date}_cc{cloud_cover}.tiff" # Include cloud cover in filename
        filepath = os.path.join(download_dir, filename)
        if not os.path.exists(filepath):
            download_single_image(token, bbox, date, filepath)
            
    return True

def download_single_image(token, bbox, date, filepath):
    process_url = "https://sh.dataspace.copernicus.eu/api/v1/process"
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json', 'Accept': 'image/tiff'}
    payload = {
        "input": {
            "bounds": {"bbox": bbox, "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}},
            "data": [{"type": "sentinel-2-l2a", "dataFilter": {"timeRange": {"from": f"{date}T00:00:00Z", "to": f"{date}T23:59:59Z"}}}]
        },
        "output": {"width": 512, "height": 512, "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}]},
        "evalscript": NDVI_EVALSCRIPT
    }
    
    try:
        print(f"Downloading NDVI data for {date}...")
        response = requests.post(process_url, headers=headers, json=payload)
        response.raise_for_status()
        with open(filepath, 'wb') as f:
            f.write(response.content)
        print(f"✓ Successfully downloaded: {os.path.basename(filepath)}")
    except requests.exceptions.RequestException as e:
        print(f"✗ Error downloading NDVI for {date}: {e}")


# --- 4. DATA PROCESSING (from analysis.py) ---
def read_tiff(file_path):
    with rasterio.open(file_path) as src:
        data = src.read(1).astype('float32')
        nodata = src.nodata
        if nodata is not None:
            data[data == nodata] = np.nan
        return data, src.profile

def find_all_images(data_dir):
    """Finds all TIFF files in a directory."""
    image_paths = []
    for file in os.listdir(data_dir):
        if file.endswith(".tiff"):
            image_paths.append(os.path.join(data_dir, file))
    return sorted(image_paths)

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
    print(f"Composite image saved to: {output_path}")

# --- 5. MAIN CONTROLLER ---
def process_request(bbox, output_path):
    """
    Main controller function. It ensures the best 10 images from the last 5 years
    are available locally and then creates a single max composite from them.
    """
    try:
        bbox_str = "_".join(map(str, bbox))
        location_data_dir = os.path.join(BASE_DATA_DIR, bbox_str)
        os.makedirs(location_data_dir, exist_ok=True)

        # We always check for new, better images from the server.
        print("Authenticating to check for the latest and best images...")
        token = get_access_token()
        if not token:
            return False, "Failed to authenticate with Copernicus."
        
        # This function will find the best 10 images and download them if not present.
        get_best_images_for_bbox(token, bbox, location_data_dir)

        # Get all images available locally for that location (should be our 10 best)
        image_files = find_all_images(location_data_dir)

        if not image_files:
             return False, "Sufficient data could not be found or downloaded."
        
        print(f"\nCreating a max composite from {len(image_files)} available images.")
        create_composite_image(image_files, output_path, method='max')
        
        return True, output_path

    except Exception as e:
        print(f"An error occurred in process_request: {e}")
        return False, str(e)
