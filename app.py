import os
import re
import secrets
import sqlite3
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "civicpulse_secret_key_2026")

app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024
UPLOAD_FOLDER = os.path.join(app.root_path, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

DATABASE = "civicpulse.db"

ISO_COUNTRIES = {
    "United States": "US", "India": "IN", "United Kingdom": "GB", "Canada": "CA",
    "Australia": "AU", "Germany": "DE", "France": "FR"
}

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                occupation TEXT NOT NULL,
                password_hash TEXT NOT NULL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_auth (
                username TEXT PRIMARY KEY,
                country_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                is_first_login INTEGER DEFAULT 1
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS complaints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                complaint_id_str TEXT UNIQUE NOT NULL,
                user_email TEXT NOT NULL,
                country TEXT NOT NULL,
                country_code TEXT NOT NULL,
                state TEXT NOT NULL,
                city TEXT NOT NULL,
                latitude REAL,
                longitude REAL,
                category TEXT NOT NULL,
                complaint_text TEXT NOT NULL,
                attachment_filename TEXT,
                priority_score INTEGER NOT NULL,
                urgency_label TEXT NOT NULL,
                matched_keywords TEXT NOT NULL,
                status TEXT DEFAULT 'Pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        default_hash = generate_password_hash("abcgov")
        for country, code in ISO_COUNTRIES.items():
            cursor.execute("SELECT * FROM admin_auth WHERE username = ?", (code,))
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO admin_auth (username, country_name, password_hash, is_first_login) VALUES (?, ?, ?, 1)",
                    (code, country, default_hash)
                )
        conn.commit()

init_db()

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"success": False, "message": "File exceeds maximum upload limit of 500 MB!"}), 413

def generate_complaint_id(country_code):
    fifteen_digit_num = secrets.randbelow(9 * 10**14) + 10**14
    return f"{country_code}-{fifteen_digit_num}"

SEVERITY_WEIGHTS = {"CRITICAL": 35, "HIGH": 20, "MEDIUM": 10}
LEXICON = {
    "CRITICAL": [
        r"\bdeath[s]?\b", r"\bfatal(ity|ities)?\b", r"\bpoison(ing|ed)?\b", r"\barsenic\b", 
        r"\btoxic\b", r"\bcollapse[d]?\b", r"\belectrocution\b", r"\bexplosion\b", 
        r"\bevacuat(e|ion)\b", r"\bepidemic\b", r"\bcontamination\b", r"\bcasualty\b"
    ],
    "HIGH": [
        r"\bsewage\b", r"\bflood(ing)?\b", r"\bburst\b", r"\bhazard\b", r"\blandslide\b", 
        r"\bblackout\b", r"\bshortage\b", r"\bblockade\b", r"\bleakage\b", r"\binfection\b"
    ],
    "MEDIUM": [
        r"\bpothole[s]?\b", r"\bcrack[s]?\b", r"\bdelay[s]?\b", r"\bgarbage\b", 
        r"\bstench\b", r"\bbroken\b", r"\bdarkness\b", r"\bnoise\b", r"\bmaintenance\b"
    ]
}

def analyze_complaint_heuristics(text):
    text_lower = text.lower()
    score = 10
    detected = []

    for level, patterns in LEXICON.items():
        for pattern in patterns:
            matches = re.findall(pattern, text_lower)
            if matches:
                count = len(matches)
                score += SEVERITY_WEIGHTS[level] * count
                clean_kw = pattern.replace(r"\b", "").replace("[s]?", "").replace("(ing)?", "")
                detected.append(f"{clean_kw} (x{count})")

    score = min(score, 100)
    label = "CRITICAL" if score >= 70 else "HIGH" if score >= 45 else "MEDIUM" if score >= 25 else "LOW"
    return score, label, ", ".join(detected) if detected else "None detected"

@app.route("/")
def index():
    if "user" in session:
        return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/api/signup", methods=["POST"])
def signup():
    data = request.json or {}
    name, email, occupation, password = data.get("name"), data.get("email"), data.get("occupation"), data.get("password")

    if not name or not email or not occupation or not password:
        return jsonify({"success": False, "message": "All fields are required!"}), 400

    hashed_pw = generate_password_hash(password)
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (name, email, occupation, password_hash) VALUES (?, ?, ?, ?)",
                           (name, email, occupation, hashed_pw))
            conn.commit()
        session["user"] = email
        return jsonify({"success": True, "message": "Signup successful!"})
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "Email already registered!"}), 400

@app.route("/api/login", methods=["POST"])
def login():
    data = request.json or {}
    email, password = data.get("email"), data.get("password")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()

    if user and check_password_hash(user["password_hash"], password):
        session["user"] = email
        return jsonify({"success": True, "message": "Login successful!"})
    
    return jsonify({"success": False, "message": "Invalid credentials!"}), 401

@app.route("/api/logout", methods=["POST"])
def logout():
    session.pop("user", None)
    return jsonify({"success": True})

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("index"))
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name, email, occupation FROM users WHERE email = ?", (session["user"],))
        user_record = cursor.fetchone()

    if not user_record:
        session.pop("user", None)
        return redirect(url_for("index"))

    return render_template("dashboard.html", user=dict(user_record))

@app.route("/api/user/complaints")
def get_user_complaints():
    if "user" not in session:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT complaint_id_str, country, state, city, latitude, longitude, category, 
                   priority_score, urgency_label, matched_keywords, status, created_at, attachment_filename
            FROM complaints WHERE user_email = ? ORDER BY id DESC
        """, (session["user"],))
        rows = cursor.fetchall()

    return jsonify({"success": True, "complaints": [dict(r) for r in rows]})

@app.route("/api/submit_complaint", methods=["POST"])
def submit_complaint():
    if "user" not in session:
        return jsonify({"success": False, "message": "Unauthorized access."}), 401

    country = request.form.get("country", "").strip()
    state = request.form.get("state", "").strip()
    city = request.form.get("city", "").strip()
    category = request.form.get("category", "").strip()
    complaint_text = request.form.get("complaint_text", "").strip()
    lat = request.form.get("latitude", type=float)
    lng = request.form.get("longitude", type=float)

    word_count = len(complaint_text.split())
    if word_count < 100 or word_count > 20000:
        return jsonify({
            "success": False, 
            "message": f"Word count must be between 100 and 20,000 words. Current count: {word_count} words."
        }), 400

    attachment_filename = None
    if 'attachment' in request.files:
        file = request.files['attachment']
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            unique_prefix = secrets.token_hex(4)
            attachment_filename = f"{unique_prefix}_{filename}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], attachment_filename))

    country_code = ISO_COUNTRIES.get(country, country[:2].upper() if len(country) >= 2 else "XX")
    complaint_id_str = generate_complaint_id(country_code)
    score, label, keywords = analyze_complaint_heuristics(complaint_text)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO complaints 
            (complaint_id_str, user_email, country, country_code, state, city, latitude, longitude, category, complaint_text, attachment_filename, priority_score, urgency_label, matched_keywords, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending')
        """, (complaint_id_str, session["user"], country, country_code, state, city, lat, lng, category, complaint_text, attachment_filename, score, label, keywords))
        conn.commit()

    return jsonify({
        "success": True,
        "complaint_id": complaint_id_str,
        "priority_score": score,
        "urgency_label": label,
        "keywords_detected": keywords
    })

@app.route("/admin")
def admin_page():
    return render_template("admin.html")

@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.json or {}
    username = data.get("username", "").strip().upper()
    password = data.get("password")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username, country_name, password_hash, is_first_login FROM admin_auth WHERE username = ?", (username,))
        record = cursor.fetchone()

    if record and check_password_hash(record["password_hash"], password):
        session["admin_user"] = record["username"]
        session["admin_country_code"] = record["username"]
        session["admin_country_name"] = record["country_name"]
        return jsonify({
            "success": True,
            "must_change_password": bool(record["is_first_login"]),
            "country_code": record["username"]
        })

    return jsonify({"success": False, "message": "Invalid Country Code or Password."}), 401

@app.route("/api/admin/change_password", methods=["POST"])
def admin_change_password():
    if not session.get("admin_user"):
        return jsonify({"success": False, "message": "Unauthorized."}), 401

    data = request.json or {}
    new_password = data.get("new_password")

    if not new_password or len(new_password) < 6:
        return jsonify({"success": False, "message": "Password must be at least 6 characters."}), 400

    new_hash = generate_password_hash(new_password)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE admin_auth SET password_hash = ?, is_first_login = 0 WHERE username = ?",
                       (new_hash, session["admin_user"]))
        conn.commit()

    return jsonify({"success": True, "message": "Password successfully updated!"})

@app.route("/api/admin/complaints")
def get_admin_complaints():
    if not session.get("admin_user"):
        return jsonify({"success": False, "message": "Unauthorized access."}), 401

    country_code = session.get("admin_country_code")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT complaint_id_str, user_email, country, state, city, latitude, longitude, category, complaint_text, 
                   attachment_filename, priority_score, urgency_label, matched_keywords, status, created_at
            FROM complaints
            WHERE country_code = ?
            ORDER BY priority_score DESC, id DESC
        """, (country_code,))
        rows = cursor.fetchall()

    return jsonify({"success": True, "country_code": country_code, "complaints": [dict(r) for r in rows]})

@app.route("/api/admin/update_status", methods=["POST"])
def update_complaint_status():
    if not session.get("admin_user"):
        return jsonify({"success": False, "message": "Unauthorized access."}), 401

    data = request.json or {}
    complaint_id = data.get("complaint_id")
    new_status = data.get("status")

    if new_status not in ["Pending", "Resolved", "Not Important", "Rejected"]:
        return jsonify({"success": False, "message": "Invalid status value."}), 400

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE complaints SET status = ? WHERE complaint_id_str = ? AND country_code = ?",
                       (new_status, complaint_id, session.get("admin_country_code")))
        conn.commit()

    return jsonify({"success": True, "message": f"Status updated to '{new_status}'"})

@app.route("/api/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("admin_user", None)
    session.pop("admin_country_code", None)
    return jsonify({"success": True})

if __name__ == "__main__":
    app.run(debug=True, port=5000)