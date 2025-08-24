import requests
import os
import json
from datetime import datetime, timedelta
import base64

# --- 1. CONFIGURATION ---
# IMPORTANT: Replace with your actual Client ID and Secret
CLIENT_ID = "sh-61654116-66e8-45f4-a553-50ad0a07929a"
CLIENT_SECRET = "Tusibl8GSpjCDDWJOgO85GINHTv93GAG"

# Area of Interest (AOI) for Pune, India
# Bounding box coordinates [min_lon, min_lat, max_lon, max_lat]
PUNE_BBOX = [73.75, 18.40, 74.00, 18.65]

# Define the date range for the past 5 years
end_date = datetime.now()
start_date = end_date - timedelta(days=5*365) # Approximate for 5 years
START_DATE_STR = start_date.strftime("%Y-%m-%d")
END_DATE_STR = end_date.strftime("%Y-%m-%d")

# Create a base directory to save the downloaded files
BASE_DOWNLOAD_DIR = "pune_ndvi_data"
os.makedirs(BASE_DOWNLOAD_DIR, exist_ok=True)

# --- 2. AUTHENTICATION ---
def get_access_token(client_id, client_secret):
    """Fetches an access token from the Copernicus Identity Server."""
    auth_url = 'https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token'
    auth_data = {
        'client_id': client_id,
        'client_secret': client_secret,
        'grant_type': 'client_credentials'
    }
    try:
        response = requests.post(auth_url, data=auth_data)
        response.raise_for_status()
        print("Authentication successful.")
        return response.json()['access_token']
    except requests.exceptions.RequestException as e:
        print(f"Error during authentication: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response content: {e.response.text}")
        return None

# --- 3. NDVI EVALSCRIPT ---
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
    // Calculate NDVI: (NIR - Red) / (NIR + Red)
    let ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04);
    
    // Filter out clouds, cloud shadows, and other unwanted pixels
    if (sample.SCL == 3 || sample.SCL == 8 || sample.SCL == 9 || sample.SCL == 10 || sample.SCL == 11) {
        return [NaN]; // Cloud, cloud shadow, or snow
    }
    
    return [ndvi];
}
"""

# --- 4. SEARCH FOR NDVI DATA ---
def search_ndvi_dates(token, bbox, start_date, end_date):
    """Search for available Sentinel-2 dates."""
    search_url = "https://sh.dataspace.copernicus.eu/api/v1/catalog/1.0.0/search"
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    search_payload = {
        "bbox": bbox,
        "datetime": f"{start_date}T00:00:00Z/{end_date}T23:59:59Z",
        "collections": ["sentinel-2-l2a"],
        "limit": 100
    }
    
    try:
        response = requests.post(search_url, headers=headers, json=search_payload)
        response.raise_for_status()
        features = response.json().get('features', [])
        print(f"Found {len(features)} Sentinel-2 scenes (limit 100 per search)")
        return features
    except requests.exceptions.RequestException as e:
        print(f"Error during date search: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response content: {e.response.text}")
        return []

# --- 5. DOWNLOAD NDVI DATA ---
def download_ndvi_data(token, bbox, date, filename, download_dir):
    """Download NDVI data for a specific date using Sentinel Hub Process API."""
    process_url = "https://sh.dataspace.copernicus.eu/api/v1/process"
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'Accept': 'image/tiff'
    }
    
    # Process API payload
    payload = {
        "input": {
            "bounds": {
                "bbox": bbox,
                "properties": {
                    "crs": "http://www.opengis.net/def/crs/EPSG/0/4326"
                }
            },
            "data": [{
                "type": "sentinel-2-l2a",
                "dataFilter": {
                    "timeRange": {
                        "from": f"{date}T00:00:00Z",
                        "to": f"{date}T23:59:59Z"
                    }
                }
            }]
        },
        "output": {
            "width": 1000,  # Adjust resolution as needed
            "height": 1000,
            "responses": [{
                "identifier": "default",
                "format": {
                    "type": "image/tiff"
                }
            }]
        },
        "evalscript": NDVI_EVALSCRIPT
    }
    
    try:
        print(f"Downloading NDVI data for {date}...")
        response = requests.post(process_url, headers=headers, json=payload)
        response.raise_for_status()
        
        filepath = os.path.join(download_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(response.content)
        
        print(f"✓ Successfully downloaded: {filename}")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"✗ Error downloading NDVI for {date}: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response content: {e.response.text}")
        return False

# --- 6. DOWNLOAD TIME SERIES NDVI ---
def download_time_series_ndvi(token, bbox, start_date, end_date, download_dir):
    """Download NDVI time series data."""
    process_url = "https://sh.dataspace.copernicus.eu/api/v1/process"
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'Accept': 'application/tar'
    }
    
    # Process API payload for time series
    payload = {
        "input": {
            "bounds": {
                "bbox": bbox,
                "properties": {
                    "crs": "http://www.opengis.net/def/crs/EPSG/0/4326"
                }
            },
            "data": [{
                "type": "sentinel-2-l2a",
                "dataFilter": {
                    "timeRange": {
                        "from": f"{start_date}T00:00:00Z",
                        "to": f"{end_date}T23:59:59Z"
                    }
                },
                "processing": {
                    "harmonizeValues": True
                }
            }]
        },
        "output": {
            "width": 1000,
            "height": 1000,
            "responses": [{
                "identifier": "default",
                "format": {
                    "type": "image/tiff"
                }
            }]
        },
        "evalscript": NDVI_EVALSCRIPT
    }
    
    try:
        print("Downloading NDVI time series data...")
        response = requests.post(process_url, headers=headers, json=payload)
        response.raise_for_status()
        
        filepath = os.path.join(download_dir, f"pune_ndvi_timeseries_{start_date}_to_{end_date}.tar")
        with open(filepath, 'wb') as f:
            f.write(response.content)
        
        print(f"✓ Successfully downloaded time series: {filepath}")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"✗ Error downloading NDVI time series: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response content: {e.response.text}")
        return False

# --- 7. MAIN EXECUTION ---
if __name__ == "__main__":
    if CLIENT_ID == "YOUR_CLIENT_ID" or CLIENT_SECRET == "YOUR_CLIENT_SECRET":
        print("Please replace 'YOUR_CLIENT_ID' and 'YOUR_CLIENT_SECRET' with your actual credentials.")
    else:
        print(f"Fetching NDVI data for Pune for the last 5 years ({START_DATE_STR} to {END_DATE_STR})")
        print(f"Bounding Box: {PUNE_BBOX}")
        
        end_date_obj = datetime.now()
        
        # Loop through the past 5 years
        for i in range(5):
            year_num = i + 1
            print(f"\n--- Processing Year {year_num} ---")

            # Get a fresh access token for each year to prevent expiration
            access_token = get_access_token(CLIENT_ID, CLIENT_SECRET)
            if not access_token:
                print(f"Failed to authenticate for year {year_num}. Skipping.")
                # We still need to update the date for the next iteration
                end_date_obj -= timedelta(days=365)
                continue

            start_date_obj = end_date_obj - timedelta(days=365)
            
            # Define strings for the current year's date range
            start_date_str_year = start_date_obj.strftime("%Y-%m-%d")
            end_date_str_year = end_date_obj.strftime("%Y-%m-%d")
            
            # Create a specific directory for the current year
            year_dir_name = f"past_{year_num}_year"
            year_download_dir = os.path.join(BASE_DOWNLOAD_DIR, year_dir_name)
            os.makedirs(year_download_dir, exist_ok=True)
            
            # --- Option 1: Download time series (recommended) ---
            print(f"\n=== Downloading NDVI Time Series for past year {year_num} ({start_date_str_year} to {end_date_str_year}) ===")
            success = download_time_series_ndvi(access_token, PUNE_BBOX, start_date_str_year, end_date_str_year, year_download_dir)
            
            if success:
                print(f"\n✓ NDVI time series data for year {year_num} saved to: {year_download_dir}")
                print("\nTo extract and analyze the data:")
                print(f"1. Navigate to the {year_download_dir} directory")
                print(f"2. Extract the TAR file: tar -xf pune_ndvi_timeseries_*.tar")
                print("3. Use GIS software (QGIS, ArcGIS) or Python libraries (rasterio, GDAL) to analyze the TIFF files")

            # --- Option 2: Search and download individual dates (alternative approach) ---
            print(f"\n=== Alternative for year {year_num}: Searching for specific dates ===")
            available_dates = search_ndvi_dates(access_token, PUNE_BBOX, start_date_str_year, end_date_str_year)
            
            if available_dates:
                print(f"Found {len(available_dates)} suitable dates for year {year_num}")
                # Download all dates found, not just the first 5
                for j, feature in enumerate(available_dates):
                    date = feature['properties']['datetime'][:10]  # Extract date
                    filename = f"pune_ndvi_{date}.tiff"
                    download_ndvi_data(access_token, PUNE_BBOX, date, filename, year_download_dir)
            
            # Set the end date for the next iteration to the start date of the current one
            end_date_obj = start_date_obj

        print("\n🎉 All downloads completed!")
