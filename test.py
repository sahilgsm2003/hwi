import requests
import os
from datetime import datetime, timedelta

# --- 1. CONFIGURATION ---
# IMPORTANT: Replace with your actual Client ID and Secret
# Get these from your Copernicus Data Space Ecosystem Dashboard -> OAuth clients
CLIENT_ID = "sh-61654116-66e8-45f4-a553-50ad0a07929a"
CLIENT_SECRET = "Tusibl8GSpjCDDWJOgO85GINHTv93GAG"

# Area of Interest (AOI) for Pune, India in WKT format
# This is a bounding box that covers the Pune metropolitan area.
PUNE_AOI = "POLYGON((73.75 18.65, 74.00 18.65, 74.00 18.40, 73.75 18.40, 73.75 18.65))"

# Define the date range for the past year
end_date = datetime.now()
start_date = end_date - timedelta(days=365)
START_DATE_STR = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
END_DATE_STR = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")

# Create a directory to save the downloaded files
DOWNLOAD_DIR = "pune_sentinel_data"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

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
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)
        print("Authentication successful.")
        return response.json()['access_token']
    except requests.exceptions.RequestException as e:
        print(f"Error during authentication: {e}")
        print(f"Response content: {response.text}")
        return None

# --- 3. DATA SEARCH ---
def search_for_products(token, aoi, start_date, end_date):
    """Searches for Sentinel-2 L2A products for a given area and time."""
    search_api_url = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"

    # Filter for Sentinel-2, Level-2A products with cloud cover less than 10%
    query_filter = (
        f"OData.CSC.Intersects(area=geography'SRID=4326;{aoi}') and "
        f"ContentDate/Start gt {start_date} and "
        f"ContentDate/Start lt {end_date} and "
        f"Collection/Name eq 'Sentinel2' and "
        f"contains(Name, 'S2MSI2A') and "
        f"Attributes/OData.CSC.DoubleAttribute/any(att: att/Name eq 'cloudCover' and att/Value lt 10)"
    )

    params = {
        "$filter": query_filter,
        "$top": 100 # Max results
    }

    headers = {'Authorization': f'Bearer {token}'}

    print("Searching for available products...")
    try:
        response = requests.get(search_api_url, headers=headers, params=params)
        response.raise_for_status()
        products = response.json().get('value', [])
        print(f"Found {len(products)} products matching the criteria.")
        return products
    except requests.exceptions.RequestException as e:
        print(f"Error during product search: {e}")
        print(f"Response content: {response.text}")
        return []

# --- 4. DATA DOWNLOAD ---
def download_product(token, product_id, product_name):
    """Downloads a single product by its ID."""
    download_url = f"https://zipper.dataspace.copernicus.eu/odata/v1/Products({product_id})/$value"
    headers = {'Authorization': f'Bearer {token}'}
    filepath = os.path.join(DOWNLOAD_DIR, f"{product_name}.zip")

    if os.path.exists(filepath):
        print(f"File {product_name}.zip already exists. Skipping.")
        return

    print(f"Starting download for {product_name}...")
    try:
        with requests.get(download_url, headers=headers, stream=True) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            with open(filepath, 'wb') as f:
                downloaded = 0
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    # Progress bar logic
                    downloaded += len(chunk)
                    done = int(50 * downloaded / total_size)
                    print(f"\r[{'=' * done}{' ' * (50-done)}] {downloaded / (1024*1024):.2f} MB / {total_size / (1024*1024):.2f} MB", end='')
        print("\nDownload complete.")
    except requests.exceptions.RequestException as e:
        print(f"\nError downloading {product_name}: {e}")
        # Clean up partially downloaded file
        if os.path.exists(filepath):
            os.remove(filepath)

# --- 5. MAIN EXECUTION ---
if __name__ == "__main__":
    if CLIENT_ID == "YOUR_CLIENT_ID" or CLIENT_SECRET == "YOUR_CLIENT_SECRET":
        print("Please replace 'YOUR_CLIENT_ID' and 'YOUR_CLIENT_SECRET' with your actual credentials.")
    else:
        access_token = get_access_token(CLIENT_ID, CLIENT_SECRET)
        if access_token:
            products_to_download = search_for_products(access_token, PUNE_AOI, START_DATE_STR, END_DATE_STR)
            if products_to_download:
                for i, product in enumerate(products_to_download):
                    print(f"\n--- Processing product {i+1}/{len(products_to_download)} ---")
                    product_id = product['Id']
                    product_name = product['Name']
                    download_product(access_token, product_id, product_name)
                print("\nAll downloads finished.")
            else:
                print("No products to download.")
