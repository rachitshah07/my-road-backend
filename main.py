from flask import Flask, render_template, request, jsonify
from PIL import Image, ExifTags
from pillow_heif import register_heif_opener
import os
import tempfile
from flask_cors import CORS

register_heif_opener()
app = Flask(__name__)
CORS(app)

def dms_to_decimal(degrees, minutes, seconds, ref):
    print("dms-to-decimal")
    value = degrees + minutes / 60 + seconds / 3600
    if ref in ['S', 'W']:
        value = -value
    return value

def extract_gps_info(exif_data):
    print(">>> [extract_gps_info] Called.")
    gps_info = exif_data.get(34853)
    print(f">>> [extract_gps_info] GPSInfo tag: {gps_info}")
    if not gps_info or not isinstance(gps_info, dict):
        print(">>> [extract_gps_info] No GPS metadata present in EXIF.")
        return None
    gps_data = {}
    for key in gps_info.keys():
        name = ExifTags.GPSTAGS.get(key, key)
        gps_data[name] = gps_info[key]
    if all(k in gps_data for k in ('GPSLatitude', 'GPSLatitudeRef', 'GPSLongitude', 'GPSLongitudeRef')):
        print(">>> [extract_gps_info] Found all required GPS fields.")
        lat = gps_data['GPSLatitude']
        lat_ref = gps_data['GPSLatitudeRef']
        lon = gps_data['GPSLongitude']
        lon_ref = gps_data['GPSLongitudeRef']
        print(f">>> [extract_gps_info] lat={lat}, lat_ref={lat_ref} | lon={lon}, lon_ref={lon_ref}")
        def get_num(x):
            return float(x[0]) / float(x[1]) if isinstance(x, tuple) else float(x)
        lat_deg = get_num(lat[0])
        lat_min = get_num(lat[1])
        lat_sec = get_num(lat[2])
        lon_deg = get_num(lon[0])
        lon_min = get_num(lon[1])
        lon_sec = get_num(lon[2])
        print(f">>> [extract_gps_info] Normalized lat: {lat_deg}, {lat_min}, {lat_sec}")
        print(f">>> [extract_gps_info] Normalized lon: {lon_deg}, {lon_min}, {lon_sec}")
        latitude = dms_to_decimal(lat_deg, lat_min, lat_sec, lat_ref)
        longitude = dms_to_decimal(lon_deg, lon_min, lon_sec, lon_ref)
        print(f">>> [extract_gps_info] Converted coords: latitude={latitude}, longitude={longitude}")
        return {'latitude': latitude, 'longitude': longitude}
    print(">>> [extract_gps_info] Not all required GPS fields present in GPSInfo tag.")
    return None

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/upload", methods=["POST"])
def upload():
    print(">>> [upload] POST /upload hit")
    uploaded_file = request.files.get("image")
    print(f">>> [upload] uploaded_file: {uploaded_file.filename if uploaded_file else 'None'}")
    user_lat = request.form.get('user_lat')
    user_lon = request.form.get('user_lon')
    print(f">>> [upload] Form user_lat: {user_lat}, user_lon: {user_lon}")

    if not uploaded_file:
        print(">>> [upload] No image uploaded!")
        return jsonify({"error": "No image uploaded!", "source": "none"}), 400

    with tempfile.NamedTemporaryFile(delete=False, dir="/tmp") as tmp:
        tmp_path = tmp.name
        uploaded_file.save(tmp_path)
    print(f">>> [upload] Image temporarily saved at {tmp_path}")

    try:
        print(">>> [upload] Opening image for EXIF extraction...")
        image = Image.open(tmp_path)
        exif_data = image.getexif()
        print(f">>> [upload] Got EXIF: {bool(exif_data)}")
        coords = extract_gps_info(exif_data)
    except Exception as e:
        print(f">>> [upload] Exception in extracting EXIF: {e}")
        coords = None
    finally:
        os.remove(tmp_path)
        print(f">>> [upload] Temp file {tmp_path} removed.")

    if coords:
        print(">>> [upload] Using EXIF GPS data.")
        result = {
            "found_gps": True,
            "source": "image_exif",
            "latitude": coords['latitude'],
            "longitude": coords['longitude']
        }
    elif user_lat and user_lon:
        try:
            lat = float(user_lat)
            lon = float(user_lon)
            print(">>> [upload] Using fallback device geolocation data.")
        except (TypeError, ValueError):
            lat, lon = None, None
            print(">>> [upload] Fallback device geolocation failed (bad input).")
        result = {
            "found_gps": False,
            "source": "device_current",
            "latitude": lat,
            "longitude": lon
        }
    else:
        print(">>> [upload] No GPS data available from image EXIF or device.")
        result = {
            "found_gps": False,
            "source": "none",
            "latitude": None,
            "longitude": None
        }
    print(f">>> [upload] Returning result: {result}")
    return jsonify(result)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
