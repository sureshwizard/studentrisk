from flask import Flask, render_template, request, redirect, jsonify
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os
from openai import OpenAI

# -------------------------
# APP
# -------------------------
app = Flask(__name__, static_folder="static")

# -------------------------
# GOOGLE SHEETS
# -------------------------
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_name("creds.json", scope)
client = gspread.authorize(creds)
wb = client.open("Student_Risk_Platform")

# -------------------------
# OPENAI
# -------------------------
OPENAI_KEY = os.getenv("OPENAI_KEY")
client_ai = OpenAI(api_key=OPENAI_KEY)

# -------------------------
# TABLES
# -------------------------
TABLES = [
    "student_master",
    "attendance_risk",
    "academic_risk",
    "financial_risk",
    "behavior_risk",
    "engagement_risk",
    "wellbeing_risk",
    "family_risk",
    "ml_features",
    "ai_risk_score",
    "risk_rules"
]

# -------------------------
# FAVICON
# -------------------------
@app.route("/favicon.ico")
def favicon():
    return app.send_static_file("favicon.ico")

# -------------------------
# HOME
# -------------------------
@app.route("/")
def home():
    return redirect("/dashboard")

# -------------------------
# DASHBOARD
# -------------------------
@app.route("/dashboard")
def dashboard():
    students = wb.worksheet("student_master").get_all_records()
    ai = wb.worksheet("ai_risk_score").get_all_records()

    merged = []

    for s in students:
        for a in ai:
            if str(s.get("student_id")) == str(a.get("student_id")):
                merged.append({
                    "student_id": s.get("student_id"),
                    "name": s.get("name"),
                    "risk": a.get("risk_category"),
                    "score": float(a.get("overall_risk_score", 0))
                })

    top = sorted(merged, key=lambda x: x["score"], reverse=True)[:10]

    high = sum(1 for x in merged if x["risk"] == "HIGH")
    medium = sum(1 for x in merged if x["risk"] == "MEDIUM")
    low = sum(1 for x in merged if x["risk"] == "LOW")

    return render_template(
        "dashboard.html",
        top=top,
        high=high,
        medium=medium,
        low=low,
        tables=TABLES
    )

# -------------------------
# TABLE VIEW
# -------------------------
@app.route("/table/<name>")
def table(name):
    sheet = wb.worksheet(name)
    data = sheet.get_all_values()
    return render_template("list.html", table=name, headers=data[0], rows=data[1:], tables=TABLES)

# -------------------------
# ADD RECORD
# -------------------------
@app.route("/add/<name>", methods=["GET", "POST"])
def add(name):
    sheet = wb.worksheet(name)
    headers = sheet.row_values(1)

    if request.method == "POST":
        row = []
        for h in headers:
            if h in ["last_updated", "last_calculated"]:
                row.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            else:
                row.append(request.form.get(h, ""))
        sheet.append_row(row)
        return redirect(f"/table/{name}")

    return render_template("form.html", table=name, headers=headers, tables=TABLES)

# -------------------------
# DELETE
# -------------------------
@app.route("/delete/<name>/<int:row>")
def delete(name, row):
    wb.worksheet(name).delete_rows(row + 1)
    return redirect(f"/table/{name}")

# -------------------------
# 🔥 AI ROUTER
# -------------------------
@app.route("/ask", methods=["GET", "POST"])
def ask():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        q = data.get("question", "").strip()
    else:
        q = request.args.get("q", "").strip()

    if not q:
        return jsonify({"answer": "Please ask a question."})

    q_lower = q.lower()

    triggers = ["suresh", "chatbot", "hi", "studentrisk", "student risk", "riskai", "risk ai"]
    DATA_MODE = False

    for t in triggers:
        if q_lower.startswith(t):
            DATA_MODE = True
            q = q[len(t):].strip()
            break

    students = wb.worksheet("student_master").get_all_records()
    ai = wb.worksheet("ai_risk_score").get_all_records()

    rows = []
    for s in students:
        for a in ai:
            if str(s.get("student_id")) == str(a.get("student_id")):
                rows.append(
                    f"{s.get('student_id')},{s.get('name')},{s.get('grade')},{s.get('school')},"
                    f"{a.get('risk_category')},{a.get('overall_risk_score')},"
                    f"{a.get('attendance_score')},{a.get('academic_score')},"
                    f"{a.get('financial_score')},{a.get('behavior_score')},"
                    f"{a.get('engagement_score')},{a.get('wellbeing_score')}"
                )

    dataset = "\n".join(rows)

    if not dataset:
        return jsonify({"answer": "No student risk data found in Google Sheets."})

    if DATA_MODE:
        system = "You are StudentRisk AI. You must answer ONLY from the dataset. Do not hallucinate."
    else:
        system = "You are a helpful assistant."

    prompt = f"""{system}

student_id,name,grade,school,risk,overall,attendance,academic,financial,behavior,engagement,wellbeing
{dataset}

Question: {q}
"""

    try:
        res = client_ai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        answer = res.choices[0].message.content
    except Exception as e:
        answer = "AI error: " + str(e)

    return jsonify({"answer": answer})

# -------------------------
# START
# -------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=4090)

