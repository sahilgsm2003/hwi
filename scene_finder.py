import requests
from datetime import datetime, timedelta
from fpdf import FPDF
import os
import rasterio
import numpy as np
import matplotlib.pyplot as plt

# --- 1. CONFIGURATION ---
# Enter the coordinates you want to analyze here
LATITUDE = 28.7041  # Example: Delhi
LONGITUDE = 77.1025 # Example: Delhi

# !!! IMPORTANT SAFETY LIMIT !!!
# This script will download one image for EACH scene found. For 5 years, this can be 500+ images.
# We are limiting it to the first 20 scenes as a safety measure.
# Change this value if you want to process more, or set to a large number (e.g., 999) to process all.
MAX_SCENES_TO_PROCESS = 20

# Directory to store temporary images
TEMP_IMAGE_DIR = "temp_scene_images"

# Copernicus API Credentials
CLIENT_ID = "sh-61654116-66e8-45f4-a553-50ad0a07929a"
CLIENT_SECRET = "Tusibl8GSpjCDDWJOgO85GINHTv93GAG"


def get_access_token():
    """Fetches an access token from the Copernicus Identity Server."""
    auth_url = 'https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token'
    auth_data = {'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'grant_type': 'client_credentials'}
    try:
        response = requests.post(auth_url, data=auth_data)
        response.raise_for_status()
        print("✓ Authentication successful.\n")
        return response.json()['access_token']
    except requests.exceptions.RequestException as e:
        print(f"✗ Error during authentication: {e}")
        return None

def find_all_scenes_metadata(token, lat, lon):
    """
    Finds and returns all available Sentinel-2 scenes for a given
    location over the past 5 years.
    """
    bbox = [lon - 0.125, lat - 0.125, lon + 0.125, lat + 0.125]
    today = datetime.now()
    all_scenes = []

    for i in range(5):
        end_date = today - timedelta(days=i * 365)
        start_date = end_date - timedelta(days=365)
        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")
        
        year_key = f"{start_date.year}-{end_date.year}"
        print(f"--- Searching scenes for {year_key} ---")
        
        search_url = "https://sh.dataspace.copernicus.eu/api/v1/catalog/1.0.0/search"
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        search_payload = {
            "bbox": bbox,
            "datetime": f"{start_date_str}T00:00:00Z/{end_date_str}T23:59:59Z",
            "collections": ["sentinel-2-l2a"],
            "limit": 100  # Get up to 100 scenes per year
        }
        
        try:
            response = requests.post(search_url, headers=headers, json=search_payload)
            response.raise_for_status()
            features = response.json().get('features', [])
            
            if not features:
                print("No scenes found for this period.")
                continue

            # Sort by date
            features.sort(key=lambda f: f['properties']['datetime'])
            
            all_scenes.extend(features)
            print(f"Found {len(features)} scenes.\n")

        except requests.exceptions.RequestException as e:
            print(f"Could not search for year {year_key}: {e}\n")
            continue
            
    all_scenes.sort(key=lambda f: f['properties']['datetime'])
    return all_scenes

def download_single_image(token, bbox, date, filepath):
    """Downloads a single Sentinel-2 scene as a GeoTIFF."""
    process_url = "https://sh.dataspace.copernicus.eu/api/v1/process"
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json', 'Accept': 'image/tiff'}
    payload = {
        "input": { "bounds": {"bbox": bbox, "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}}, "data": [{"type": "sentinel-2-l2a", "dataFilter": {"timeRange": {"from": f"{date}T00:00:00Z", "to": f"{date}T23:59:59Z"}}}]},
        "output": {"width": 256, "height": 256, "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}]}, # Smaller images for PDF
        "evalscript": "return [B04, B03, B02];" # Natural color evalscript
    }
    try:
        response = requests.post(process_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        with open(filepath, 'wb') as f: f.write(response.content)
        return True
    except requests.exceptions.RequestException as e:
        print(f"  ✗ Error downloading {filepath}: {e}")
        return False

def convert_tiff_to_png(tiff_path, png_path):
    """Converts a GeoTIFF to a displayable PNG."""
    try:
        with rasterio.open(tiff_path) as src:
            # Read the 3 bands (RGB)
            data = src.read((1, 2, 3)).astype(np.float32)
            # Normalize each band to 0-255 for display
            for i in range(data.shape[0]):
                band = data[i]
                min_val, max_val = np.nanmin(band), np.nanmax(band)
                if min_val < max_val:
                    data[i] = ((band - min_val) / (max_val - min_val)) * 255
            # Transpose from (band, height, width) to (height, width, band) for saving
            rgb_data = np.transpose(data, (1, 2, 0)).astype(np.uint8)
            plt.imsave(png_path, rgb_data)
        return True
    except Exception as e:
        print(f"  ✗ Could not convert {tiff_path} to PNG: {e}")
        return False

def generate_visual_report(token, all_scenes, lat, lon):
    """Downloads images for each scene and generates a PDF with images."""
    if not os.path.exists(TEMP_IMAGE_DIR):
        os.makedirs(TEMP_IMAGE_DIR)

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, f"Visual Scene Report for ({lat}, {lon})", ln=True, align="C")
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 5, f"Showing first {min(len(all_scenes), MAX_SCENES_TO_PROCESS)} of {len(all_scenes)} total scenes found.", ln=True, align="C")
    pdf.ln(10)
    
    bbox = [lon - 0.125, lat - 0.125, lon + 0.125, lat + 0.125]
    
    scenes_processed = 0
    for scene in all_scenes:
        if scenes_processed >= MAX_SCENES_TO_PROCESS:
            print(f"\nReached safety limit of {MAX_SCENES_TO_PROCESS} scenes.")
            break
        
        date = scene['properties']['datetime'][:10]
        cloud_cover = scene['properties'].get('eo:cloud_cover', -1)
        
        print(f"Processing scene from {date}...")
        
        tiff_filename = f"{date}_cc{cloud_cover:.2f}.tiff"
        png_filename = f"{date}_cc{cloud_cover:.2f}.png"
        tiff_path = os.path.join(TEMP_IMAGE_DIR, tiff_filename)
        png_path = os.path.join(TEMP_IMAGE_DIR, png_filename)

        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, f"Date: {date}  |  Cloud Cover: {cloud_cover:.2f}%", ln=True)

        if download_single_image(token, bbox, date, tiff_path):
            if convert_tiff_to_png(tiff_path, png_path):
                # Add image to PDF, maintaining aspect ratio
                pdf.image(png_path, x=15, w=pdf.w - 30)
                pdf.ln(5)
            else:
                pdf.set_font("Arial", "I", 10)
                pdf.cell(0, 8, "    (Image conversion failed)", ln=True)
        else:
            pdf.set_font("Arial", "I", 10)
            pdf.cell(0, 8, "    (Image download failed)", ln=True)
            
        scenes_processed += 1
        
    output_filename = f"visual_scene_report_for_{lat}_{lon}.pdf"
    pdf.output(output_filename)
    print(f"\n✓ Visual PDF report saved as '{output_filename}'")
    print(f"ℹ Temporary images are stored in the '{TEMP_IMAGE_DIR}' directory.")

if __name__ == "__main__":
    print(f"Starting visual scene analysis for Latitude: {LATITUDE}, Longitude: {LONGITUDE}")
    access_token = get_access_token()
    if access_token:
        # 1. Find metadata for ALL scenes
        all_scenes_meta = find_all_scenes_metadata(access_token, LATITUDE, LONGITUDE)
        
        # 2. Generate the visual report (with the safety limit)
        if all_scenes_meta:
            generate_visual_report(access_token, all_scenes_meta, LATITUDE, LONGITUDE)
        else:
            print("No scenes found to generate a report.")
