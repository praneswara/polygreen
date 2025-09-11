from flask import Flask, request, jsonify
from flask_cors import CORS
import datetime as dt

app = Flask(__name__)
CORS(app)

# ---------------- Demo user ----------------
DEMO_USER = {
    "id": 0,
    "name": "BUSANTECH",
    "mobile": 1234567890,
    "points": 100,
    "bottles": 10,
    "created_at": dt.datetime.utcnow().isoformat()
}

# ---------------- Auth ---------------------
@app.route("/api/auth/login", methods=["POST"])
def login():
    return jsonify(
        access_token="dummy-token",
        user=DEMO_USER
    )


@app.route("/api/auth/register", methods=["POST"])
def register():
    return jsonify(message="Registered"), 201


# ---------------- User ---------------------
@app.route("/api/users/me", methods=["GET"])
def me():
    return jsonify(DEMO_USER)


# ---------------- Points -------------------
@app.route("/api/points/summary", methods=["GET"])
def points_summary():
    return jsonify(
        total_points=DEMO_USER["points"],
        recent=[
            {"id": 1, "points": 20, "created_at": dt.datetime.utcnow().isoformat(), "type": "earn"},
            {"id": 2, "points": -50, "created_at": dt.datetime.utcnow().isoformat(), "type": "redeem"}
        ]
    )


@app.route("/api/transactions", methods=["GET"])
def transactions():
    return jsonify(items=[
        {"id": 1, "type": "earn", "points": 20, "brand_id": None,
         "machine_id": "M001", "created_at": dt.datetime.utcnow().isoformat()},
        {"id": 2, "type": "redeem", "points": 50, "brand_id": 1,
         "machine_id": None, "created_at": dt.datetime.utcnow().isoformat()}
    ])


# ---------------- Redeem -------------------
@app.route("/api/redeem/brands", methods=["GET"])
def redeem_brands():
    return jsonify(items=[
        {"id": 1, "name": "Amazon", "min_points": 200},
        {"id": 2, "name": "Flipkart", "min_points": 150},
        {"id": 3, "name": "Swiggy", "min_points": 100}
    ])


@app.route("/api/redeem/request", methods=["POST"])
def redeem_request():
    return jsonify(message="Redeem successful", coupon="AMZ-0-0001")


# ---------------- Machines -----------------
@app.route("/api/machine/insert", methods=["POST"])
def machine_insert():
    return jsonify(
        message="Points and bottles added successfully",
        earned_points=10,
        bottles_added=1,
        user_total_points=DEMO_USER["points"] + 10,
        user_total_bottles=DEMO_USER["bottles"] + 1,
        machine_current_bottles=11,
        machine_available_space=89,
        machine_is_full=False
    )


@app.route("/api/machines", methods=["GET"])
def list_machines():
    return jsonify(items=[
        {
            "id": 1,
            "machine_id": "M001",
            "name": "RVM Station A",
            "city": "jim,korea",
            "lat": 10.823879417459477,
            "lng": 78.70024710440879,
            "current_bottles": 10,
            "max_capacity": 100,
            "available_space": 90,
            "is_full": False,
            "last_emptied": None
        },
        {
            "id": 2,
            "machine_id": "M002",
            "name": "RVM Station B",
            "city": "jim,korea",
            "lat": 12.9352,
            "lng": 77.6245,
            "current_bottles": 20,
            "max_capacity": 100,
            "available_space": 80,
            "is_full": False,
            "last_emptied": None
        }
    ])


# ---------------- Root ---------------------
@app.route("/", methods=["GET"])
def home():
    return jsonify(message="Demo Polygreen API running (no DB)")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

