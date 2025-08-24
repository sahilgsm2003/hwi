# Satellite Vegetation Analysis API

This project provides a powerful set of tools to analyze vegetation changes over time using Sentinel-2 satellite imagery. It includes a Flask API for on-demand processing and standalone scripts for data exploration.

## Features

- **Time-Series Analysis**: Generate cloud-free, yearly composite images for any location to analyze long-term trends in deforestation and urbanization.
- **Dynamic Seasonal Window**: Intelligently analyzes 5 years of historical data to find the clearest 3-month "dry season" for any given location, ensuring high-quality, comparable data.
- **On-Demand Processing**: A simple REST API that accepts coordinates or place names to trigger the analysis pipeline.
- **Scene Availability Reporting**: A standalone tool (`scene_finder.py`) to quickly generate a report of all available satellite scenes for a location over the past 5 years, complete with metadata and visual previews.
- **Geocoding**: The API can convert place names (e.g., "Delhi, India") into coordinates automatically.

---

## Setup and Installation

### Prerequisites

- Python 3.8+
- `pip` for package management

### 1. Clone the Repository (Optional)

If you have this project in a git repository, clone it:

```bash
git clone <your-repo-url>
cd <your-repo-directory>
```

### 2. Install Dependencies

Install all the required Python libraries using the `requirements.txt` file.

```powershell
pip install -r requirements.txt
```

### 3. Configure API Credentials

The application requires API credentials from the Copernicus Data Space Ecosystem.

- Open the `data_manager.py` file.
- Replace the placeholder values for `CLIENT_ID` and `CLIENT_SECRET` with your actual credentials.

```python
# data_manager.py

# --- 1. CONFIGURATION ---
CLIENT_ID = "sh-..."  # <-- YOUR CLIENT ID HERE
CLIENT_SECRET = "..." # <-- YOUR CLIENT SECRET HERE
```

---

## Usage Guide

### A) The Main API: Generating Yearly Composites

This is the core feature of the project. The API will generate a set of clean, seasonally-consistent composite images for a range of years, ready for comparison.

#### 1. Start the Server

Run the `app.py` file to start the Flask web server.

```powershell
python app.py
```

The server will start and be available at `http://127.0.0.1:5000`.

#### 2. Call the API Endpoint

Use a tool like `curl` or any API client to make a `GET` request to the `/generate_yearly_composites` endpoint.

**Endpoint:** `GET /generate_yearly_composites`

**Parameters:**

- `start_year` (int): The first year of the analysis period.
- `end_year` (int): The last year of the analysis period.
- `lat` & `lon` (float): The latitude and longitude for the center of the area.
  **OR**
- `place` (str): A place name (e.g., "Mumbai, India").

**Example 1: Using Coordinates**

```powershell
curl "http://127.0.0.1:5000/generate_yearly_composites?start_year=2022&end_year=2024&lat=28.7041&lon=77.1025"
```

**Example 2: Using a Place Name**

```powershell
curl "http://127.0.0.1:5000/generate_yearly_composites?start_year=2023&end_year=2025&place=Pune, India"
```

#### 3. Understanding the Output

- **In the Terminal**: You will see a detailed log as the application finds the optimal season and then processes each year.
- **API Response**: The API will return a JSON object detailing the results, including the file paths for each composite image created and any years that were skipped due to lack of data.
- **Output Files**: The final composite `.tiff` images will be saved in the `output/` directory.

---

### B) The Scene Finder Tool

This is a standalone script for exploring what data is available for a location _before_ you commit to a full analysis run. It generates a detailed PDF report.

#### 1. Configure the Location

Open the `scene_finder.py` script and edit the `LATITUDE` and `LONGITUDE` variables at the top of the file.

```python
# scene_finder.py

LATITUDE = 28.7041  # Example: Delhi
LONGITUDE = 77.1025 # Example: Delhi
```

#### 2. Run the Script

Execute the script directly from your terminal.

```powershell
python scene_finder.py
```

#### 3. Understanding the Output

- **In the Terminal**: The script will print a summary of all scenes found.
- **PDF Report**: A PDF file named `visual_scene_report_for_LAT_LON.pdf` will be created in the project root. This PDF contains a visual preview and metadata for each scene found (up to a safety limit defined in the script).
- **Temporary Images**: The downloaded preview images are stored in the `temp_scene_images/` directory.

---

## Project Structure

```
.
├── app.py                  # Main Flask API server
├── data_manager.py         # Core logic for data downloading, processing, and compositing
├── scene_finder.py         # Standalone tool for generating scene availability reports
├── requirements.txt        # Python dependencies
├── data/                   # (Generated) Cache for raw downloaded satellite TIFFs
├── output/                 # (Generated) Final output composite TIFFs from the API
├── temp_scene_images/      # (Generated) Temporary images for the scene finder PDF report
└── README.md               # This file
```
