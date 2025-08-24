import requests
import os
from datetime import datetime, timedelta

# --- 1. CONFIGURATION ---
# IMPORTANT: Replace with your actual Client ID and Secret
CLIENT_ID = "sh-61654116-66e8-45f4-a553-50ad0a07929a"
CLIENT_SECRET = "Tusibl8GSpjCDDWJOgO85GINHTv93GAG"

# Area of Interest (AOI) for Pune, India in WKT format
PUNE_AOI = "POLYGON((73.75 18.65, 74.00 18.65, 74.00 18.40, 73.75 18.40, 73.75 18.65))"

# Define the date range for the past year
end_date = datetime.now()
start_date = end_date - timedelta(days=365)
START_DATE_STR = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
END_DATE_STR = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")

# Create a directory to save the downloaded files
DOWNLOAD_DIR = "pune_clms_ndvi_data"
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
        response.raise_for_status()
        print("Authentication successful.")
        return response.json()['access_token']
    except requests.exceptions.RequestException as e:
        print(f"Error during authentication: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response content: {e.response.text}")
        return None

# --- 3. SEARCH FOR CLMS NDVI PRODUCTS ---
def search_clms_ndvi_products(token, aoi, start_date, end_date):
    """Searches for CLMS NDVI products for a given area and time."""
    search_api_url = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"

    # Try different CLMS NDVI collection patterns
    clms_collections = [
        "CLMS_HRVPP_VPP_NDVI_GLOBAL_010M_V2", # Current high-resolution NDVI
        "CLMS_HRVPP_VPP_NDVI_GLOBAL_001KM_V2", # 1km resolution NDVI
        "CLMS_HRVPP_VPP_NDVI_300M_V2",  # 300m resolution NDVI
        "CLMS_HRVPP_VPP_NDVI_GLOBAL_V2",  # General NDVI collection
    ]
    
    all_products = []
    
    for collection_name in clms_collections:
        print(f"Searching for {collection_name}...")
        
        # Filter for CLMS NDVI products
        query_filter = (
            f"OData.CSC.Intersects(area=geography'SRID=4326;{aoi}') and "
            f"ContentDate/Start gt {start_date} and "
            f"ContentDate/Start lt {end_date} and "
            f"contains(Collection/Name, 'CLMS') and "
            f"contains(Name, 'NDVI')"
        )

        params = {
            "$filter": query_filter,
            "$top": 100  # Max results
        }

        headers = {'Authorization': f'Bearer {token}'}

        try:
            response = requests.get(search_api_url, headers=headers, params=params)
            response.raise_for_status()
            products = response.json().get('value', [])
            print(f"Found {len(products)} products for {collection_name}")
            all_products.extend(products)
        except requests.exceptions.RequestException as e:
            print(f"Error searching {collection_name}: {e}")
            continue
    
    # Remove duplicates based on product ID
    unique_products = {product['Id']: product for product in all_products}
    final_products = list(unique_products.values())
    
    print(f"Total unique CLMS NDVI products found: {len(final_products)}")
    return final_products

# --- 4. ALTERNATIVE SEARCH: Browse Collections First ---
def browse_clms_collections(token):
    """Browse available CLMS collections to find correct NDVI collection names."""
    collections_url = "https://catalogue.dataspace.copernicus.eu/odata/v1/Collections"
    
    headers = {'Authorization': f'Bearer {token}'}
    
    # Search for collections containing CLMS and NDVI
    params = {
        "$filter": "contains(Name, 'CLMS') or contains(Description, 'NDVI')",
        "$top": 50
    }
    
    try:
        response = requests.get(collections_url, headers=headers, params=params)
        response.raise_for_status()
        collections = response.json().get('value', [])
        
        print(f"\n=== Available CLMS/NDVI Collections ===")
        for collection in collections:
            print(f"Name: {collection['Name']}")
            print(f"Description: {collection.get('Description', 'No description')[:100]}...")
            print("-" * 50)
        
        return collections
    except requests.exceptions.RequestException as e:
        print(f"Error browsing collections: {e}")
        return []

# --- 5. SEARCH BY SPECIFIC COLLECTION ---
def search_by_collection_name(token, collection_name, aoi, start_date, end_date):
    """Search for products in a specific collection."""
    search_api_url = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
    
    query_filter = (
        f"OData.CSC.Intersects(area=geography'SRID=4326;{aoi}') and "
        f"ContentDate/Start gt {start_date} and "
        f"ContentDate/Start lt {end_date} and "
        f"Collection/Name eq '{collection_name}'"
    )

    params = {
        "$filter": query_filter,
        "$top": 100
    }

    headers = {'Authorization': f'Bearer {token}'}

    try:
        response = requests.get(search_api_url, headers=headers, params=params)
        response.raise_for_status()
        products = response.json().get('value', [])
        print(f"Found {len(products)} products in collection: {collection_name}")
        return products
    except requests.exceptions.RequestException as e:
        print(f"Error searching collection {collection_name}: {e}")
        return []

# --- 6. DATA DOWNLOAD ---
def download_product(token, product_id, product_name):
    """Downloads a single product by its ID."""
    download_url = f"https://zipper.dataspace.copernicus.eu/odata/v1/Products({product_id})/$value"
    headers = {'Authorization': f'Bearer {token}'}
    
    # Clean filename
    safe_name = "".join(c for c in product_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
    filepath = os.path.join(DOWNLOAD_DIR, f"{safe_name}.zip")

    if os.path.exists(filepath):
        print(f"File {safe_name}.zip already exists. Skipping.")
        return True

    print(f"Starting download for {safe_name}...")
    try:
        with requests.get(download_url, headers=headers, stream=True) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            with open(filepath, 'wb') as f:
                downloaded = 0
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        done = int(50 * downloaded / total_size)
                        print(f"\r[{'=' * done}{' ' * (50-done)}] {downloaded / (1024*1024):.2f} MB / {total_size / (1024*1024):.2f} MB", end='')
        print("\nDownload complete.")
        return True
    except requests.exceptions.RequestException as e:
        print(f"\nError downloading {safe_name}: {e}")
        if os.path.exists(filepath):
            os.remove(filepath)
        return False

# --- 7. MAIN EXECUTION ---
if __name__ == "__main__":
    if CLIENT_ID == "YOUR_CLIENT_ID" or CLIENT_SECRET == "YOUR_CLIENT_SECRET":
        print("Please replace 'YOUR_CLIENT_ID' and 'YOUR_CLIENT_SECRET' with your actual credentials.")
    else:
        print(f"Searching for CLMS NDVI data for Pune from {START_DATE_STR} to {END_DATE_STR}")
        
        access_token = get_access_token(CLIENT_ID, CLIENT_SECRET)
        if access_token:
            # First, browse available collections to understand what's available
            print("\n=== Step 1: Browsing available CLMS collections ===")
            collections = browse_clms_collections(access_token)
            
            # Try to find NDVI products using different approaches
            print("\n=== Step 2: Searching for NDVI products ===")
            ndvi_products = search_clms_ndvi_products(access_token, PUNE_AOI, START_DATE_STR, END_DATE_STR)
            
            if not ndvi_products and collections:
                # If no products found, try searching specific collections
                print("\n=== Step 3: Trying specific collections ===")
                for collection in collections:
                    if any(keyword in collection['Name'].upper() for keyword in ['NDVI', 'VPP', 'VEGETATION']):
                        print(f"Trying collection: {collection['Name']}")
                        products = search_by_collection_name(
                            access_token, 
                            collection['Name'], 
                            PUNE_AOI, 
                            START_DATE_STR, 
                            END_DATE_STR
                        )
                        ndvi_products.extend(products)
            
            if ndvi_products:
                print(f"\n=== Step 4: Downloading {len(ndvi_products)} NDVI products ===")
                successful_downloads = 0
                for i, product in enumerate(ndvi_products[:10]):  # Limit to first 10 products
                    print(f"\n--- Processing product {i+1}/{min(len(ndvi_products), 10)} ---")
                    print(f"Product: {product['Name']}")
                    print(f"Date: {product.get('ContentDate', {}).get('Start', 'Unknown')}")
                    
                    if download_product(access_token, product['Id'], product['Name']):
                        successful_downloads += 1
                
                print(f"\n🎉 Successfully downloaded {successful_downloads} NDVI products to {DOWNLOAD_DIR}")
                
                if successful_downloads > 0:
                    print("\nNext steps:")
                    print("1. Extract the ZIP files to access the NDVI raster data")
                    print("2. Use GIS software (QGIS) or Python (rasterio/GDAL) to analyze the data")
                    print("3. The NDVI values typically range from -1 to +1")
                    print("   - Values > 0.3 indicate healthy vegetation")
                    print("   - Values < 0.1 indicate sparse or no vegetation")
            else:
                print("\n❌ No CLMS NDVI products found for the specified criteria.")
                print("\nThis could mean:")
                print("1. CLMS NDVI data might not be available through OData API")
                print("2. Collection names might be different than expected")
                print("3. Use the Sentinel Hub approach (pune_ndvi_download.py) instead")
        else:
            print("Failed to authenticate. Please check your credentials.")
