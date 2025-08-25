from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os

app = Flask(__name__)
app.secret_key = "chama_secret_key"

DB_NAME = "chama.db"

# ------------------ DATABASE SETUP ------------------
def init_db():
    if not os.path.exists(DB_NAME):
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        # Members
        c.execute("""
            CREATE TABLE members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT,
                phone TEXT
            )
        """)
        # Contributions
        c.execute("""
            CREATE TABLE contributions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_id INTEGER,
                amount REAL,
                date TEXT,
                FOREIGN KEY(member_id) REFERENCES members(id)
            )
        """)
        # Loans
        c.execute("""
            CREATE TABLE loans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_id INTEGER,
                amount REAL,
                date TEXT,
                status TEXT DEFAULT 'active',
                FOREIGN KEY(member_id) REFERENCES members(id)
            )
        """)
        # Loan repayments
        c.execute("""
            CREATE TABLE repayments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                loan_id INTEGER,
                amount REAL,
                date TEXT,
                FOREIGN KEY(loan_id) REFERENCES loans(id)
            )
        """)
        conn.commit()
        conn.close()

init_db()

# ------------------ LOGIN ------------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        # simple demo login
        if username == "admin" and password == "admin":
            session["user"] = username
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid username or password", "danger")

    return render_template("login.html")

# ------------------ DASHBOARD ------------------
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Members
    c.execute("SELECT COUNT(*) FROM members")
    total_members = c.fetchone()[0]

    # Contributions
    c.execute("SELECT IFNULL(SUM(amount), 0) FROM contributions")
    total_contributions = c.fetchone()[0]

    # Loans
    c.execute("SELECT IFNULL(SUM(amount), 0) FROM loans WHERE status='active'")
    active_loans = c.fetchone()[0]

    # Repayments
    c.execute("SELECT IFNULL(SUM(amount), 0) FROM repayments")
    total_repayments = c.fetchone()[0]

    conn.close()

    return render_template(
        "dashboard.html",
        total_members=total_members,
        total_contributions=total_contributions,
        active_loans=active_loans,
        total_repayments=total_repayments
    )

# ------------------ ADD MEMBER ------------------
@app.route("/add_member", methods=["GET", "POST"])
def add_member():
    if "user" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        phone = request.form["phone"]

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT INTO members (name, email, phone) VALUES (?, ?, ?)", (name, email, phone))
        conn.commit()
        conn.close()
        flash("Member added successfully", "success")
        return redirect(url_for("dashboard"))

    return render_template("add_member.html")

# ------------------ ADD CONTRIBUTION ------------------
@app.route("/add_contribution", methods=["GET", "POST"])
def add_contribution():
    if "user" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, name FROM members")
    members = c.fetchall()
    conn.close()

    if request.method == "POST":
        member_id = request.form["member_id"]
        amount = request.form["amount"]
        date = request.form["date"]

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT INTO contributions (member_id, amount, date) VALUES (?, ?, ?)",
                  (member_id, amount, date))
        conn.commit()
        conn.close()
        flash("Contribution recorded", "success")
        return redirect(url_for("dashboard"))

    return render_template("add_contribution.html", members=members)

# ------------------ ADD LOAN ------------------
@app.route("/add_loan", methods=["GET", "POST"])
def add_loan():
    if "user" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, name FROM members")
    members = c.fetchall()
    conn.close()

    if request.method == "POST":
        member_id = request.form["member_id"]
        amount = request.form["amount"]
        date = request.form["date"]

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT INTO loans (member_id, amount, date) VALUES (?, ?, ?)", (member_id, amount, date))
        conn.commit()
        conn.close()
        flash("Loan issued", "success")
        return redirect(url_for("dashboard"))

    return render_template("add_loan.html", members=members)

# ------------------ REPAY LOAN ------------------
@app.route("/repay_loan", methods=["GET", "POST"])
def repay_loan():
    if "user" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, amount FROM loans WHERE status='active'")
    loans = c.fetchall()
    conn.close()

    if request.method == "POST":
        loan_id = request.form["loan_id"]
        amount = request.form["amount"]
        date = request.form["date"]

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT INTO repayments (loan_id, amount, date) VALUES (?, ?, ?)", (loan_id, amount, date))

        # update loan if fully repaid
        c.execute("SELECT SUM(amount) FROM repayments WHERE loan_id=?", (loan_id,))
        total_paid = c.fetchone()[0] or 0
        c.execute("SELECT amount FROM loans WHERE id=?", (loan_id,))
        loan_amount = c.fetchone()[0]

        if total_paid >= loan_amount:
            c.execute("UPDATE loans SET status='cleared' WHERE id=?", (loan_id,))

        conn.commit()
        conn.close()
        flash("Repayment recorded", "success")
        return redirect(url_for("dashboard"))

    return render_template("repay_loan.html", loans=loans)

# ------------------ MEMBER REPORT ------------------
@app.route("/member_report/<int:member_id>")
def member_report(member_id):
    if "user" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("SELECT name, email, phone FROM members WHERE id=?", (member_id,))
    member = c.fetchone()

    c.execute("SELECT SUM(amount) FROM contributions WHERE member_id=?", (member_id,))
    total_contributions = c.fetchone()[0] or 0

    c.execute("SELECT SUM(amount) FROM loans WHERE member_id=?", (member_id,))
    total_loans = c.fetchone()[0] or 0

    c.execute("""SELECT SUM(r.amount) 
                 FROM repayments r
                 JOIN loans l ON r.loan_id = l.id
                 WHERE l.member_id=?""", (member_id,))
    total_repaid = c.fetchone()[0] or 0

    conn.close()

    return render_template("member_report.html",
                           member=member,
                           total_contributions=total_contributions,
                           total_loans=total_loans,
                           total_repaid=total_repaid)

# ------------------ LOGOUT ------------------
@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("Logged out successfully", "info")
    return redirect(url_for("login"))

# ------------------ RUN ------------------
if __name__ == "__main__":
    app.run(debug=True)

