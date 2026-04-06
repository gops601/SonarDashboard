from flask import Flask, render_template, request, redirect, url_for, jsonify
import requests
import mysql.connector

app = Flask(__name__)

SONAR_URL = "http://187.127.142.34:9000"
TOKEN = "squ_f3e8f13c007c76c4af99412aa8fcb4b027e47c10"

DB = {
    "host": "localhost",
    "user": "root",
    "password": "Admin123",
    "database": "sonar_dashboard"
}

def db_conn():
    return mysql.connector.connect(**DB)


# -------- FETCH PROJECTS -------- #
def fetch_projects():
    try:
        r = requests.get(f"{SONAR_URL}/api/projects/search", auth=(TOKEN, ""))
        return r.json().get("components", [])
    except:
        return []


# -------- FETCH METRICS -------- #
def fetch_metrics(project_key):
    try:
        params = {
            "component": project_key,
            "metricKeys": "bugs,vulnerabilities,code_smells,coverage,duplicated_lines_density"
        }
        r = requests.get(f"{SONAR_URL}/api/measures/component", params=params, auth=(TOKEN, ""))

        data = r.json()
        metrics = {}

        for m in data.get("component", {}).get("measures", []):
            metrics[m["metric"]] = float(m.get("value", 0))

        return metrics
    except:
        return {}


# -------- FETCH QUALITY -------- #
def fetch_quality(project_key):
    try:
        r = requests.get(
            f"{SONAR_URL}/api/qualitygates/project_status",
            params={"projectKey": project_key},
            auth=(TOKEN, "")
        )
        return r.json().get("projectStatus", {}).get("status", "UNKNOWN")
    except:
        return "UNKNOWN"


# -------- FETCH RATINGS -------- #
def fetch_ratings(project_key):
    try:
        params = {
            "component": project_key,
            "metricKeys": "reliability_rating,security_rating,sqale_rating"
        }
        r = requests.get(f"{SONAR_URL}/api/measures/component", params=params, auth=(TOKEN, ""))

        data = r.json()

        rating_map = {"1.0": "A", "2.0": "B", "3.0": "C", "4.0": "D", "5.0": "E"}
        ratings = {}

        for m in data.get("component", {}).get("measures", []):
            ratings[m["metric"]] = rating_map.get(m.get("value", ""), "N/A")

        return ratings
    except:
        return {}


# -------- FETCH ISSUES -------- #
def fetch_issues(project_key):
    try:
        r = requests.get(
            f"{SONAR_URL}/api/issues/search",
            params={"componentKeys": project_key, "ps": 10},
            auth=(TOKEN, "")
        )
        return r.json().get("issues", [])
    except:
        return []


# -------- SAVE DATA -------- #
def save_data(project_key, metrics, quality, ratings, issues):
    conn = db_conn()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO metrics(project_key, bugs, vulnerabilities, code_smells, coverage, duplicated_lines)
    VALUES (%s,%s,%s,%s,%s,%s)
    """, (
        project_key,
        metrics.get("bugs", 0),
        metrics.get("vulnerabilities", 0),
        metrics.get("code_smells", 0),
        metrics.get("coverage", 0),
        metrics.get("duplicated_lines_density", 0)
    ))

    cur.execute(
        "INSERT INTO quality_gate(project_key, status) VALUES (%s,%s)",
        (project_key, quality)
    )

    cur.execute("""
    INSERT INTO ratings(project_key, reliability, security, maintainability)
    VALUES (%s,%s,%s,%s)
    """, (
        project_key,
        ratings.get("reliability_rating", "N/A"),
        ratings.get("security_rating", "N/A"),
        ratings.get("sqale_rating", "N/A")
    ))

    for issue in issues:
        cur.execute("""
        INSERT INTO issues(project_key, issue_key, severity, message, file, line)
        VALUES (%s,%s,%s,%s,%s,%s)
        """, (
            project_key,
            issue.get("key"),
            issue.get("severity"),
            issue.get("message"),
            issue.get("component"),
            issue.get("line", 0)
        ))

    conn.commit()
    cur.close()
    conn.close()


# -------- ROUTES -------- #

@app.route("/", methods=["GET"])
def dashboard():
    projects_raw = fetch_projects()
    
    grouped_projects = {}
    for p in projects_raw:
        original_name = p.get('name', 'Unknown')
        parts = original_name.split('-')
        
        if len(parts) >= 2:
            userid = parts[-1].strip()
            proj_name = "-".join(parts[:-1]).strip()
        else:
            userid = "Other"
            proj_name = original_name.strip()
            
        if userid not in grouped_projects:
            grouped_projects[userid] = []
            
        grouped_projects[userid].append({
            'key': p.get('key', ''),
            'name': proj_name,
            'original_name': original_name,
            'original_key': p.get('key', '')
        })

    return render_template("dashboard.html", grouped_projects=grouped_projects)

@app.route("/api/report/<project_key>", methods=["GET"])
def api_report(project_key):
    # Fetch latest data from SonarQube directly
    metrics = fetch_metrics(project_key)
    quality = fetch_quality(project_key)
    ratings = fetch_ratings(project_key)
    issues = fetch_issues(project_key)

    # Save to database in the background (or rather, synchronously before returning)
    try:
        save_data(project_key, metrics, quality, ratings, issues)
    except Exception as e:
        print(f"Failed to save data to DB: {e}")

    # Return as JSON to the frontend
    return jsonify({
        "metrics": metrics,
        "quality": {"status": quality},
        "ratings": ratings,
        "issues": issues,
        "project_key": project_key
    })


# -------- TRIGGER WORKFLOW ROUTE -------- #
@app.route("/api/trigger_scan", methods=["POST"])
def api_trigger_scan():
    data = request.json
    repo_url = data.get("repo_url")
    pat = data.get("pat")
    
    if not repo_url or not pat:
        return jsonify({"error": "Missing repository URL or PAT"}), 400
        
    owner = "gops601"
    repo = "SonarDashboard"
    workflow_id = "sonar.yml"
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches"
    
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {pat}"
    }
    payload = {
        "ref": "main",
        "inputs": {
            "student_repo": repo_url
        }
    }
    
    try:
        r = requests.post(url, headers=headers, json=payload)
        if r.status_code == 204:
            return jsonify({"message": f"Successfully triggered GitHub Workflow for {repo_url}!"}), 200
        else:
            return jsonify({"error": f"Failed to trigger workflow: {r.status_code} - {r.text}"}), 500
    except Exception as e:
        return jsonify({"error": f"Internal Error: {str(e)}"}), 500


if __name__ == "__main__":
    import threading
    import webbrowser
    import time

    def open_browser():
        time.sleep(1.5)
        webbrowser.open("http://127.0.0.1:5000/")
        
    threading.Thread(target=open_browser, daemon=True).start()
    app.run(debug=True, use_reloader=False)