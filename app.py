from flask import Flask, request, jsonify
import data_manager
import os

app = Flask(__name__)

# Create an 'output' directory to store the generated composite TIFFs
os.makedirs("output", exist_ok=True)

@app.route('/generate_yearly_composites', methods=['GET'])
def generate_yearly_composites():
    """
    API endpoint to generate a time-series of yearly composite images.

    Accepts query parameters:
    - start_year (int): The first year of the analysis period.
    - end_year (int): The last year of the analysis period.
    - place (str): A place name to be geocoded (e.g., "Delhi, India").
    OR
    - lat (float): Latitude of the center point.
    - lon (float): Longitude of the center point.
    """
    try:
        # --- 1. Get and validate parameters ---
        start_year = int(request.args.get('start_year'))
        end_year = int(request.args.get('end_year'))
        
        place = request.args.get('place')
        lat = request.args.get('lat')
        lon = request.args.get('lon')

        if not (place or (lat and lon)):
            return jsonify({"error": "Missing location. Please provide either 'place' or both 'lat' and 'lon'."}), 400
        
        if end_year < start_year:
            return jsonify({"error": "'end_year' must be greater than or equal to 'start_year'."}), 400

        # --- 2. Geocode place name if necessary ---
        if place:
            success, coords_or_error = data_manager.get_coords_from_place_name(place)
            if not success:
                return jsonify({"error": f"Geocoding failed: {coords_or_error}"}), 400
            lat, lon = coords_or_error
        else:
            lat, lon = float(lat), float(lon)

        # --- 3. Define Bounding Box ---
        bbox = [lon - 0.125, lat - 0.125, lon + 0.125, lat + 0.125]
        
        # --- 4. Process the data using the data_manager ---
        # This will be the main function we build in the next step.
        success, results_or_error = data_manager.generate_yearly_composites(
            bbox, start_year, end_year
        )

        if success:
            return jsonify({
                "message": f"Successfully generated {len(results_or_error.get('composites', {}))} yearly composites.",
                "results": results_or_error
            })
        else:
            return jsonify({"error": results_or_error}), 500

    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid parameter format: {e}"}), 400
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
