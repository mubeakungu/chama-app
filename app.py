from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, make_response, render_template_string
import sqlite3
from datetime import datetime
import pandas as pd
from xhtml2pdf import pisa
import os

app = Flask(__name__)
app.secret_key = 'supersecret'


# --- ADDED: always enable foreign key enforcement on each connection ---
def get_connection():
    conn = sqlite3.connect('chama.db')
    conn.execute('PRAGMA foreign_keys = ON')
    return conn
# ---------------------------------------------------------------------


def init_db():
    conn = get_connection()
    c = conn.cursor()

    # --- Helper: add column if missing ---
    def add_column_if_missing(table, column, col_def):
        c.execute(f"PRAGMA table_info({table})")
        cols = [col[1] for col in c.fetchall()]
        if column not in cols:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")

    # --- Admin table ---
    c.execute('''CREATE TABLE IF NOT EXISTS admin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        password TEXT NOT NULL
    )''')

    # --- Members table ---
    c.execute('''CREATE TABLE IF NOT EXISTS members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL
    )''')
    add_column_if_missing("members", "status", "TEXT DEFAULT 'pending'")
    # you can add more fields later:
    # add_column_if_missing("members", "email", "TEXT")
    # add_column_if_missing("members", "phone", "TEXT")

    # --- Contributions table ---
    c.execute('''CREATE TABLE IF NOT EXISTS contributions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        member_id INTEGER,
        amount REAL,
        type TEXT,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(member_id) REFERENCES members(id) ON DELETE CASCADE
    )''')
    # Example: add_column_if_missing("contributions", "notes", "TEXT")

    # --- Loans table ---
    c.execute('''CREATE TABLE IF NOT EXISTS loans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        member_id INTEGER,
        loan_type TEXT,
        principal REAL,
        interest_rate REAL,
        repayment_period INTEGER,
        issue_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(member_id) REFERENCES members(id) ON DELETE CASCADE
    )''')
    # Example: add_column_if_missing("loans", "status", "TEXT DEFAULT 'active'")

    # --- Withdrawals table ---
    c.execute('''CREATE TABLE IF NOT EXISTS withdrawals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        loan_id INTEGER,
        amount REAL,
        disbursed_date TEXT,
        FOREIGN KEY(loan_id) REFERENCES loans(id) ON DELETE CASCADE
    )''')

    # --- Loan Repayments table ---
    c.execute('''CREATE TABLE IF NOT EXISTS loan_repayments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        loan_id INTEGER,
        amount_paid REAL,
        payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(loan_id) REFERENCES loans(id) ON DELETE CASCADE
    )''')

    # --- Default admin ---
    c.execute("SELECT * FROM admin WHERE username = 'admin'")
    if not c.fetchone():
        c.execute("INSERT INTO admin (username, password) VALUES (?, ?)", ('admin', 'pass123'))

    conn.commit()
    conn.close()

def dict_factory(cursor, row):
    """Return rows as dictionaries"""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def get_all_members():
    conn = get_connection()
    conn.row_factory = dict_factory
    c = conn.cursor()
    c.execute("SELECT id, name FROM members ORDER BY name")
    rows = c.fetchall()
    conn.close()
    return rows


@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM admin WHERE username=? AND password=?", (username, password))
        admin = c.fetchone()
        conn.close()
        if admin:
            session['admin'] = True
            return redirect(url_for('dashboard'))
        else:
            return "Invalid credentials"
    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    if not session.get('admin'):
        return redirect(url_for('login'))

    conn = get_connection()
    conn.row_factory = dict_factory
    c = conn.cursor()

    # Members list for the select filter
    c.execute("SELECT id, name FROM members ORDER BY name")
    members = c.fetchall()

    # Contributions list for the table
    c.execute('''SELECT c.id, m.name AS member_name, c.type, c.amount, c.date
                 FROM contributions c
                 JOIN members m ON c.member_id = m.id
                 ORDER BY c.date DESC''')
    contributions_rows = c.fetchall()
    contributions = []
    for r in contributions_rows:
        contributions.append({
            "id": r["id"],
            "member_name": r["member_name"],
            "type": r["type"],
            "amount": r["amount"],
            "date": r["date"]
        })

    # Loans with repayments and balances
    c.execute('''SELECT l.id, m.name AS name, l.principal, l.interest_rate, l.repayment_period,
                        IFNULL(SUM(r.amount_paid), 0) AS repaid, l.issue_date
                 FROM loans l
                 JOIN members m ON m.id = l.member_id
                 LEFT JOIN loan_repayments r ON l.id = r.loan_id
                 GROUP BY l.id
                 ORDER BY l.issue_date DESC''')
    loan_rows = c.fetchall()
    loans = []

    total_loans_applied = 0
    total_loan_balance = 0
    total_interest = 0

    for r in loan_rows:
        principal = r["principal"] or 0
        rate = r["interest_rate"] or 0
        period = r["repayment_period"] or 0
        repaid = r["repaid"] or 0
        total_due = principal + (principal * rate * period)
        balance = total_due - repaid

        total_loans_applied += principal
        total_loan_balance += balance
        total_interest += (principal * rate * period)

        loans.append({
            "id": r["id"],
            "name": r["name"],
            "principal": principal,
            "total_due": total_due,
            "interest": rate,
            "repaid": repaid,
            "balance": balance,
            "date_applied": r["issue_date"]
        })

    # Chart data: contribution totals per member
    c.execute('''SELECT m.name, IFNULL(SUM(c.amount), 0) AS total
                 FROM members m
                 LEFT JOIN contributions c ON m.id = c.member_id
                 GROUP BY m.id
                 ORDER BY m.name''')
    members_summary = c.fetchall()
    chart_labels = [r["name"] for r in members_summary]
    chart_data = [r["total"] for r in members_summary]

    # Total contributions
    c.execute("SELECT IFNULL(SUM(amount), 0) AS total FROM contributions")
    total_contributions = c.fetchone()["total"]

    conn.close()

    return render_template("dashboard.html",
                           members=members,
                           contributions=contributions,
                           loans=loans,
                           chart_labels=chart_labels,
                           chart_data=chart_data,
                           total_contributions=total_contributions,
                           total_loans_applied=total_loans_applied,
                           total_interest=total_interest,
                           total_loan_balance=total_loan_balance)




@app.route('/member/<int:member_id>')
def member_summary(member_id):
    """Render dashboard but filtered to a single member's contributions and loans"""
    if not session.get('admin'):
        return redirect(url_for('login'))

    conn = get_connection()
    conn.row_factory = dict_factory
    c = conn.cursor()

    # Members list for the select filter
    c.execute("SELECT id, name FROM members ORDER BY name")
    members = c.fetchall()

    # Member name
    c.execute("SELECT name FROM members WHERE id = ?", (member_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        flash("Member not found")
        return redirect(url_for('dashboard'))
    member_name = row["name"]

    # Contributions only for this member
    c.execute('''SELECT c.id, m.name AS member_name, c.type, c.amount, c.date
                 FROM contributions c
                 JOIN members m ON c.member_id = m.id
                 WHERE c.member_id = ?
                 ORDER BY c.date DESC''', (member_id,))
    contributions_rows = c.fetchall()
    contributions = []
    for r in contributions_rows:
        contributions.append({
            "id": r["id"],
            "member_name": r["member_name"],
            "type": r["type"],
            "amount": r["amount"],
            "date": r["date"]
        })

    # Loans only for this member
    c.execute('''SELECT l.id, m.name AS name, l.principal, l.interest_rate, l.repayment_period,
                        IFNULL(SUM(r.amount_paid), 0) AS repaid, l.issue_date
                 FROM loans l
                 JOIN members m ON m.id = l.member_id
                 LEFT JOIN loan_repayments r ON l.id = r.loan_id
                 WHERE l.member_id = ?
                 GROUP BY l.id
                 ORDER BY l.issue_date DESC''', (member_id,))
    loan_rows = c.fetchall()
    loans = []
    total_loans_applied = 0
    total_loan_balance = 0
    total_interest = 0

    for r in loan_rows:
        principal = r["principal"] or 0
        rate = r["interest_rate"] or 0
        period = r["repayment_period"] or 0
        repaid = r["repaid"] or 0

        interest_amount = principal * rate * period
        total_due = principal + interest_amount
        balance = total_due - repaid

        total_loans_applied += principal
        total_loan_balance += balance
        total_interest += interest_amount

        loans.append({
            "id": r["id"],
            "name": r["name"],
            "principal": principal,
            "total_due": total_due,
            "interest": rate,
            "repaid": repaid,
            "balance": balance,
            "date_applied": r["issue_date"]
        })

    # Totals for contributions
    total_contributions = sum([c["amount"] for c in contributions])

    # Chart: just this member (single-entry chart)
    chart_labels = [member_name]
    chart_data = [total_contributions]

    conn.close()

    return render_template("dashboard.html",
                           members=members,
                           contributions=contributions,
                           loans=loans,
                           chart_labels=chart_labels,
                           chart_data=chart_data,
                           total_contributions=total_contributions,
                           total_loans_applied=total_loans_applied,
                           total_interest=total_interest,
                           total_loan_balance=total_loan_balance,
                           selected_member=member_id)



@app.route('/delete_loan/<int:loan_id>', methods=['POST'])
def delete_loan(loan_id):
    if not session.get('admin'):
        return redirect(url_for('login'))

    conn = get_connection()
    c = conn.cursor()

    # With ON DELETE CASCADE, deleting the loan will delete withdrawals & repayments automatically
    c.execute("DELETE FROM loans WHERE id = ?", (loan_id,))

    conn.commit()
    conn.close()
    flash("Loan deleted successfully.")
    return redirect(url_for('dashboard'))


# --- rest of your routes (add_member, add_contribution, add_loan, repay_loan, withdraw_loan, exports, report, etc.)
# I kept them intact from your prior code; paste them below or keep the ones you already have.

@app.route('/add_member', methods=['GET', 'POST'])
def add_member():
    if not session.get('admin'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form['name']
        conn = get_connection()
        c = conn.cursor()
        c.execute("INSERT INTO members (name) VALUES (?)", (name,))
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))
    return render_template('add_member.html')


@app.route("/manage_member", methods=["GET", "POST"])
def manage_member():
    if not session.get('admin'):
        return redirect(url_for('login'))

    conn = get_connection()
    conn.row_factory = dict_factory
    cur = conn.cursor()

    try:
        if request.method == "POST":
            member_id = request.form.get("member_id")
            action = request.form.get("action")

            if member_id and action:
                if action == "accept":
                    cur.execute("UPDATE members SET status = 'accepted' WHERE id = ?", (member_id,))
                elif action == "revoke":
                    cur.execute("UPDATE members SET status = 'revoked' WHERE id = ?", (member_id,))
                elif action == "remove":
                    cur.execute("DELETE FROM members WHERE id = ?", (member_id,))
                conn.commit()
                flash("Action completed successfully.")
                return redirect("/manage_member")

        # Use COALESCE in case status column is missing/null
        cur.execute("SELECT id, name, COALESCE(status, 'pending') as status FROM members")
        members = cur.fetchall()

        return render_template("manage_member.html", members=members)

    except Exception as e:
        conn.close()
        return f"Error in manage_member: {e}", 500
    finally:
        conn.close()

@app.route('/members')
def show_members():
    members = get_all_members()
    return render_template('members.html', members=members)


@app.route('/add_contribution', methods=['GET', 'POST'])
def add_contribution():
    if not session.get('admin'):
        return redirect(url_for('login'))

    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM members")
    members = c.fetchall()

    if request.method == 'POST':
        member_id = request.form['member_id']
        amount = float(request.form['amount'])
        contribution_type = request.form['type']
        c.execute("INSERT INTO contributions (member_id, amount, type) VALUES (?, ?, ?)",
                  (member_id, amount, contribution_type))
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))

    conn.close()
    return render_template('add_contribution.html', members=members)


@app.route('/add_loan', methods=['GET', 'POST'])
def add_loan():
    if not session.get('admin'):
        return redirect(url_for('login'))

    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM members")
    members = c.fetchall()

    if request.method == 'POST':
        member_id = request.form['member_id']
        loan_type = request.form['loan_type']
        principal = float(request.form['principal'])
        interest_rate = float(request.form['interest_rate'])
        repayment_period = int(request.form['repayment_period'])
        c.execute('''INSERT INTO loans (member_id, loan_type, principal, interest_rate, repayment_period)
                     VALUES (?, ?, ?, ?, ?)''',
                  (member_id, loan_type, principal, interest_rate, repayment_period))
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))

    conn.close()
    return render_template("add_loan.html", members=members)


@app.route('/repay_loan', methods=['GET', 'POST'])
def repay_loan():
    if not session.get('admin'):
        return redirect(url_for('login'))

    conn = get_connection()
    c = conn.cursor()
    c.execute('''SELECT loans.id, members.name, loans.principal
                 FROM loans JOIN members ON loans.member_id = members.id''')
    loans = c.fetchall()

    if request.method == 'POST':
        loan_id = request.form['loan_id']
        amount_paid = float(request.form['amount_paid'])
        c.execute("INSERT INTO loan_repayments (loan_id, amount_paid) VALUES (?, ?)", (loan_id, amount_paid))
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))

    conn.close()
    return render_template("repay_loan.html", loans=loans)


@app.route('/withdraw_loan', methods=['GET', 'POST'])
def withdraw_loan():
    if not session.get('admin'):
        return redirect(url_for('login'))

    conn = get_connection()
    c = conn.cursor()
    c.execute('''SELECT loans.id, members.name, loans.principal
                 FROM loans JOIN members ON loans.member_id = members.id''')
    loans = c.fetchall()

    if request.method == 'POST':
        loan_id = request.form['loan_id']
        amount = float(request.form['amount'])
        disbursed_date = request.form['disbursed_date']
        c.execute("INSERT INTO withdrawals (loan_id, amount, disbursed_date) VALUES (?, ?, ?)",
                  (loan_id, amount, disbursed_date))
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))

    conn.close()
    return render_template('withdraw_loan.html', loans=loans)


@app.route('/export/contributions/excel')
def export_contributions_excel():
    if not session.get('admin'):
        return redirect(url_for('login'))

    conn = get_connection()
    df = pd.read_sql_query('''
        SELECT m.name AS Member, c.amount AS Amount, c.type AS Type, c.date AS Date
        FROM contributions c JOIN members m ON c.member_id = m.id
        ORDER BY c.date DESC
    ''', conn)
    conn.close()
    file_path = "contributions_report.xlsx"
    df.to_excel(file_path, index=False)
    return send_file(file_path, as_attachment=True)


@app.route('/export/contributions/pdf')
def export_contributions_pdf():
    if not session.get('admin'):
        return redirect(url_for('login'))

    conn = get_connection()
    c = conn.cursor()
    c.execute('''SELECT m.name, c.amount, c.type, c.date
                 FROM contributions c JOIN members m ON c.member_id = m.id
                 ORDER BY c.date DESC''')
    data = c.fetchall()
    conn.close()

    html = render_template_string("""
    <html><body><h2>Contribution Report</h2><table border="1" cellspacing="0" cellpadding="5">
    <tr><th>Member</th><th>Amount</th><th>Type</th><th>Date</th></tr>
    {% for row in data %}<tr>
    <td>{{ row[0] }}</td><td>KES {{ row[1] }}</td><td>{{ row[2] }}</td><td>{{ row[3] }}</td>
    </tr>{% endfor %}</table></body></html>
    """, data=data)

    response = make_response()
    pisa.CreatePDF(html, dest=response.stream)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=contributions_report.pdf'
    return response


@app.route('/export/loans/excel')
def export_loans_excel():
    if not session.get('admin'):
        return redirect(url_for('login'))

    conn = get_connection()
    query = '''SELECT m.name AS Member, l.loan_type AS LoanType, l.principal AS Principal,
                      l.interest_rate AS InterestRate, l.repayment_period AS Period,
                      IFNULL(SUM(r.amount_paid), 0) AS Repaid, l.issue_date AS IssueDate
               FROM loans l
               JOIN members m ON l.member_id = m.id
               LEFT JOIN loan_repayments r ON l.id = r.loan_id
               GROUP BY l.id'''
    df = pd.read_sql_query(query, conn)
    conn.close()

    df['TotalDue'] = df['Principal'] + (df['Principal'] * df['InterestRate'] * df['Period'])
    df['Balance'] = df['TotalDue'] - df['Repaid']

    file_path = "loans_report.xlsx"
    df.to_excel(file_path, index=False)
    return send_file(file_path, as_attachment=True)


@app.route('/export/loans/pdf')
def export_loans_pdf():
    if not session.get('admin'):
        return redirect(url_for('login'))

    conn = get_connection()
    c = conn.cursor()
    c.execute('''SELECT m.name, l.loan_type, l.principal, l.interest_rate, l.repayment_period,
                        IFNULL(SUM(r.amount_paid), 0), l.issue_date
                 FROM loans l
                 JOIN members m ON m.id = l.member_id
                 LEFT JOIN loan_repayments r ON l.id = r.loan_id
                 GROUP BY l.id''')
    data = c.fetchall()
    conn.close()

    html = render_template_string("""
    <html><body><h2>Loan Report</h2><table border="1" cellspacing="0" cellpadding="5">
    <tr><th>Member</th><th>Loan Type</th><th>Principal</th><th>Interest</th>
        <th>Period</th><th>Repaid</th><th>Total Due</th><th>Balance</th><th>Issue Date</th></tr>
    {% for row in data %}
        {% set total_due = row[2] + (row[2] * row[3] * row[4]) %}
        {% set balance = total_due - row[5] %}
        <tr>
            <td>{{ row[0] }}</td><td>{{ row[1] }}</td><td>{{ row[2] }}</td>
            <td>{{ row[3] }}</td><td>{{ row[4] }}</td><td>{{ row[5] }}</td>
            <td>{{ total_due }}</td><td>{{ balance }}</td><td>{{ row[6] }}</td>
        </tr>
    {% endfor %}</table></body></html>
    """, data=data)

    response = make_response()
    pisa.CreatePDF(html, dest=response.stream)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=loans_report.pdf'
    return response


@app.route('/report/<int:member_id>')
def report(member_id):
    if not session.get('admin'):
        return redirect(url_for('login'))

    conn = get_connection()
    c = conn.cursor()

    c.execute("SELECT name FROM members WHERE id=?", (member_id,))
    member_row = c.fetchone()
    if not member_row:
        conn.close()
        flash("Member not found")
        return redirect(url_for('dashboard'))
    member_name = member_row[0]

    c.execute("SELECT SUM(amount) FROM contributions WHERE member_id=?", (member_id,))
    total_contributions = c.fetchone()[0] or 0

    c.execute('''SELECT id, loan_type, principal, interest_rate, repayment_period, issue_date
                 FROM loans WHERE member_id=?''', (member_id,))
    loan_data = c.fetchall()

    reports = []
    for loan in loan_data:
        loan_id, loan_type, principal, rate, period, issue_date = loan
        total_repayable = principal + (principal * rate * period)

        c.execute("SELECT SUM(amount_paid) FROM loan_repayments WHERE loan_id=?", (loan_id,))
        repaid = c.fetchone()[0] or 0

        c.execute("SELECT amount, disbursed_date FROM withdrawals WHERE loan_id=?", (loan_id,))
        withdrawal = c.fetchone()
        disbursed_amount = withdrawal[0] if withdrawal else 0
        disbursed_date = withdrawal[1] if withdrawal else "N/A"

        balance = total_repayable - repaid

        reports.append({
            "loan_type": loan_type,
            "principal": principal,
            "rate": rate,
            "period": period,
            "issue_date": issue_date,
            "disbursed_amount": disbursed_amount,
            "disbursed_date": disbursed_date,
            "repaid": repaid,
            "balance": balance,
            "total_repayable": total_repayable
        })

    conn.close()
    return render_template("member_report.html", name=member_name,
                           total_contributions=total_contributions,
                           reports=reports)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))  # default to 10000 if PORT not set
    app.run(host="0.0.0.0", port=port, debug=True)

