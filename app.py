from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, make_response, render_template_string
import sqlite3
from datetime import datetime
import pandas as pd
from xhtml2pdf import pisa

app = Flask(__name__)
app.secret_key = 'supersecret'


def init_db():
    conn = sqlite3.connect('chama.db')
    c = conn.cursor()

    # Admin
    c.execute('''CREATE TABLE IF NOT EXISTS admin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        password TEXT NOT NULL
    )''')

    # Members
    c.execute('''CREATE TABLE IF NOT EXISTS members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL
    )''')

    # Contributions
    c.execute('''CREATE TABLE IF NOT EXISTS contributions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        member_id INTEGER,
        amount REAL,
        type TEXT,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(member_id) REFERENCES members(id)
    )''')

    # Loans
    c.execute('''CREATE TABLE IF NOT EXISTS loans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        member_id INTEGER,
        loan_type TEXT,
        principal REAL,
        interest_rate REAL,
        repayment_period INTEGER,
        issue_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(member_id) REFERENCES members(id)
    )''')

    # Withdrawals
    c.execute('''CREATE TABLE IF NOT EXISTS withdrawals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        loan_id INTEGER,
        amount REAL,
        disbursed_date TEXT,
        FOREIGN KEY(loan_id) REFERENCES loans(id)
    )''')

    # Loan Repayments
    c.execute('''CREATE TABLE IF NOT EXISTS loan_repayments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        loan_id INTEGER,
        amount_paid REAL,
        payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(loan_id) REFERENCES loans(id)
    )''')

    # Default admin
    c.execute("SELECT * FROM admin WHERE username = 'admin'")
    if not c.fetchone():
        c.execute("INSERT INTO admin (username, password) VALUES (?, ?)", ('admin', 'pass123'))

    conn.commit()
    conn.close()


@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect('chama.db')
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
    conn = sqlite3.connect("chama.db")
    c = conn.cursor()

    # --- Contributions ---
    c.execute("""
        SELECT m.name, con.type, con.date, con.amount
        FROM contributions con
        JOIN members m ON con.member_id = m.id
    """)
    contributions = c.fetchall()

    c.execute("SELECT SUM(amount) FROM contributions")
    total_contributions = c.fetchone()[0] or 0

    c.execute("""
        SELECT con.type, SUM(con.amount)
        FROM contributions con
        GROUP BY con.type
    """)
    chart_data_raw = c.fetchall()
    chart_labels = [row[0] for row in chart_data_raw]
    chart_data = [row[1] for row in chart_data_raw]

    # --- Loans ---
    c.execute("""
        SELECT m.name, l.principal, l.total_due, l.repaid, 
               (l.total_due - l.repaid) AS balance, l.date_applied
        FROM loans l
        JOIN members m ON l.member_id = m.id
    """)
    loans = c.fetchall()

    c.execute("""
        SELECT SUM(principal), SUM(total_due), SUM(repaid), 
               (SUM(total_due) - SUM(repaid))
        FROM loans
    """)
    loan_totals = c.fetchone() or (0, 0, 0, 0)
    total_principal, total_due, total_repaid, total_balance = [
        x if x is not None else 0 for x in loan_totals
    ]

    conn.close()

    return render_template(
        "dashboard.html",
        contributions=contributions,
        chart_labels=chart_labels,
        chart_data=chart_data,
        loans=loans,
        total_contributions=total_contributions,
        total_principal=total_principal,
        total_due=total_due,
        total_repaid=total_repaid,
        total_balance=total_balance
    )

from flask import jsonify

@app.route('/api/dashboard')
def api_dashboard():
    if not session.get('admin'):
        return jsonify({"error": "unauthorized"}), 401

    conn = sqlite3.connect('chama.db')
    c = conn.cursor()

    c.execute('''SELECT members.name, SUM(contributions.amount)
                 FROM members LEFT JOIN contributions
                 ON members.id = contributions.member_id
                 GROUP BY members.id''')
    contributions = c.fetchall()

    c.execute('''
        SELECT m.name, l.id, l.principal, l.interest_rate, l.repayment_period,
        IFNULL(SUM(r.amount_paid), 0)
        FROM loans l
        JOIN members m ON m.id = l.member_id
        LEFT JOIN loan_repayments r ON l.id = r.loan_id
        GROUP BY l.id
    ''')
    loans = c.fetchall()
    conn.close()

    loan_data = []
    for name, loan_id, principal, rate, period, repaid in loans:
        total_due = principal + (principal * rate * period)
        balance = total_due - repaid
        loan_data.append([name, principal, total_due, repaid, balance])

    return jsonify({
        "members": contributions,
        "loans": loan_data
    })



@app.route('/add_member', methods=['GET', 'POST'])
def add_member():
    if not session.get('admin'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form['name']
        conn = sqlite3.connect('chama.db')
        c = conn.cursor()
        c.execute("INSERT INTO members (name) VALUES (?)", (name,))
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))
    return render_template('add_member.html')


@app.route("/manage_member", methods=["GET", "POST"])
def manage_member():
    conn = sqlite3.connect("chama.db")  # ✅ fixed
    cur = conn.cursor()
    
    if request.method == "POST":
        member_id = request.form["member_id"]
        action = request.form["action"]

        if action == "accept":
            cur.execute("UPDATE members SET status = 'accepted' WHERE id = ?", (member_id,))
        elif action == "revoke":
            cur.execute("UPDATE members SET status = 'revoked' WHERE id = ?", (member_id,))
        elif action == "remove":
            cur.execute("DELETE FROM loans WHERE member_id = ?", (member_id,))
            cur.execute("DELETE FROM members WHERE id = ?", (member_id,))

        conn.commit()
        conn.close()
        flash("Action completed successfully.")
        return redirect("/manage_member")

    cur.execute("SELECT id, name FROM members")
    members = cur.fetchall()
    conn.close()
    return render_template("manage_member.html", members=members)


@app.route('/members')
def show_members():
    members = get_all_members()  # Retrieve members from your database
    return render_template('members.html', members=members)


@app.route('/add_contribution', methods=['GET', 'POST'])
def add_contribution():
    if not session.get('admin'):
        return redirect(url_for('login'))

    conn = sqlite3.connect('chama.db')
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

    conn = sqlite3.connect('chama.db')
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

    conn = sqlite3.connect('chama.db')
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

    conn = sqlite3.connect('chama.db')
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

    conn = sqlite3.connect('chama.db')
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

    conn = sqlite3.connect('chama.db')
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

    conn = sqlite3.connect('chama.db')
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

    conn = sqlite3.connect('chama.db')
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

    conn = sqlite3.connect('chama.db')
    c = conn.cursor()

    c.execute("SELECT name FROM members WHERE id=?", (member_id,))
    member_name = c.fetchone()[0]

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


if __name__ == '__main__':
    init_db()
    app.run(host='192.168.2.117', port=5000, debug=True)

