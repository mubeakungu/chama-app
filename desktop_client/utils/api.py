import requests

BASE_URL = "http://127.0.0.1:5000"  # Replace with your Flask server IP

session = requests.Session()

def login_admin(username, password):
    try:
        r = session.post(f"{BASE_URL}/", data={'username': username, 'password': password})
        return r.url.endswith("/dashboard")  # success if redirected
    except:
        return False

def fetch_dashboard_data():
    try:
        r = session.get(f"{BASE_URL}/api/dashboard")
        if r.status_code == 200:
            # NOTE: Your Flask app must return JSON for this
            return r.json()  # You must change your Flask /dashboard to return jsonify
        return None
    except:
        return None
