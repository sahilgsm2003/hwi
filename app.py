from flask import Flask, request, jsonify
import data_manager
import os

app = Flask(__name__)

# Create an 'output' directory to store the generated composite TIFFs
os.makedirs("output", exist_ok=True)

@app.route('/process', methods=['GET'])
def process_data():
    """
    API endpoint to process NDVI data for a given location.
    It finds the best 10 cloud-free images from the past 5 years and
    creates a single max composite TIFF.
    Accepts: lat, lon as query parameters.
    """
    try:
        # --- 1. Get and validate parameters ---
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))

        if not all([lat, lon]):
            return jsonify({"error": "Missing required parameters: lat, lon"}), 400

        # --- 2. Define Bounding Box and Output Path ---
        bbox = [lon - 0.125, lat - 0.125, lon + 0.125, lat + 0.125]
        
        output_filename = f"composite_max_5year_{lat}_{lon}.tiff"
        output_path = os.path.join("output", output_filename)

        # --- 3. Process the data using the data_manager ---
        success, result_path_or_error = data_manager.process_request(bbox, output_path)

        if success:
            return jsonify({
                "message": "Processing successful. Composite of best 10 images from the last 5 years created.",
                "output_file": result_path_or_error
            })
        else:
            return jsonify({"error": result_path_or_error}), 500

    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid parameter format: {e}"}), 400
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
