import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3

def init_db():
    conn = sqlite3.connect("chama.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT,
        email TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS contributions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        member_id INTEGER,
        amount REAL,
        date TEXT,
        FOREIGN KEY (member_id) REFERENCES members (id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS loans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        member_id INTEGER,
        amount REAL,
        date TEXT,
        status TEXT,
        FOREIGN KEY (member_id) REFERENCES members (id)
    )''')
    conn.commit()
    conn.close()

# run auto-init when app starts
init_db()


app = Flask(__name__)
app.secret_key = "chama_secret_key"

DB_NAME = "chama.db"


def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def index():
    return redirect(url_for("dashboard"))


@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    conn = get_db_connection()
    c = conn.cursor()

    # Totals
    c.execute("SELECT SUM(amount) AS total_contributions FROM contributions")
    total_contributions = c.fetchone()["total_contributions"] or 0

    c.execute("SELECT SUM(amount) AS total_loans, SUM(interest) AS total_interest FROM loans")
    loan_data = c.fetchone()
    total_loans = loan_data["total_loans"] or 0
    total_interest = loan_data["total_interest"] or 0

    # Loan summary
    c.execute("""
        SELECT l.id, m.name AS member_name, l.amount, l.interest, l.status, l.date
        FROM loans l
        JOIN members m ON l.member_id = m.id
    """)
    loan_summary = c.fetchall()

    # Dropdown members
    c.execute("SELECT * FROM members")
    members = c.fetchall()

    selected_member_data = None
    if request.method == "POST":
        member_id = request.form.get("member_id")
        if member_id:
            # Contributions
            c.execute("SELECT SUM(amount) AS total FROM contributions WHERE member_id = ?", (member_id,))
            total_contrib = c.fetchone()["total"] or 0

            # Loans
            c.execute("SELECT SUM(amount) AS total FROM loans WHERE member_id = ?", (member_id,))
            total_loan = c.fetchone()["total"] or 0

            # Loan Status
            c.execute("SELECT status FROM loans WHERE member_id = ?", (member_id,))
            statuses = [row["status"] for row in c.fetchall()]

            selected_member_data = {
                "contributions": total_contrib,
                "loans": total_loan,
                "statuses": statuses,
            }

    conn.close()

    return render_template(
        "dashboard.html",
        total_contributions=total_contributions,
        total_loans=total_loans,
        total_interest=total_interest,
        loan_summary=loan_summary,
        members=members,
        selected_member_data=selected_member_data,
    )


@app.route("/add_member", methods=["GET", "POST"])
def add_member():
    if request.method == "POST":
        name = request.form["name"]
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT INTO members (name) VALUES (?)", (name,))
        conn.commit()
        conn.close()
        flash("Member added successfully!", "success")
        return redirect(url_for("dashboard"))
    return render_template("add_member.html")


@app.route("/add_contribution", methods=["GET", "POST"])
def add_contribution():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM members")
    members = c.fetchall()

    if request.method == "POST":
        member_id = request.form["member_id"]
        amount = request.form["amount"]
        c.execute("INSERT INTO contributions (member_id, amount) VALUES (?, ?)", (member_id, amount))
        conn.commit()
        conn.close()
        flash("Contribution added successfully!", "success")
        return redirect(url_for("dashboard"))

    conn.close()
    return render_template("add_contribution.html", members=members)


@app.route("/add_loan", methods=["GET", "POST"])
def add_loan():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM members")
    members = c.fetchall()

    if request.method == "POST":
        member_id = request.form["member_id"]
        amount = float(request.form["amount"])
        interest = float(request.form["interest"])
        status = request.form["status"]

        c.execute(
            "INSERT INTO loans (member_id, amount, interest, status) VALUES (?, ?, ?, ?)",
            (member_id, amount, interest, status),
        )
        conn.commit()
        conn.close()
        flash("Loan added successfully!", "success")
        return redirect(url_for("dashboard"))

    conn.close()
    return render_template("add_loan.html", members=members)


@app.route("/delete_loan/<int:loan_id>", methods=["POST"])
def delete_loan(loan_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM loans WHERE id = ?", (loan_id,))
    conn.commit()
    conn.close()
    flash("Loan deleted successfully!", "danger")
    return redirect(url_for("dashboard"))


@app.route("/member_report/<int:member_id>")
def member_report(member_id):
    conn = get_db_connection()
    c = conn.cursor()

    c.execute("SELECT * FROM members WHERE id = ?", (member_id,))
    member = c.fetchone()

    c.execute("SELECT * FROM contributions WHERE member_id = ?", (member_id,))
    contributions = c.fetchall()

    c.execute("SELECT * FROM loans WHERE member_id = ?", (member_id,))
    loans = c.fetchall()

    conn.close()
    return render_template("member_report.html", member=member, contributions=contributions, loans=loans)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
