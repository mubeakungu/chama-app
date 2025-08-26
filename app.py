from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, make_response, render_template_string, jsonify
import sqlite3
from datetime import datetime
import pandas as pd
from xhtml2pdf import pisa
import os

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


@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if not session.get('admin'):
        return redirect(url_for('login'))

    selected_member = request.form.get("member_filter")

    conn = sqlite3.connect('chama.db')
    c = conn.cursor()

    # Members for dropdown
    c.execute("SELECT id, name FROM members")
    members = c.fetchall()

    # Contributions
    if selected_member:
        c.execute('''SELECT m.name, c.amount, c.type, c.date
                     FROM contributions c 
                     JOIN members m ON c.member_id = m.id
                     WHERE m.id = ?
                     ORDER BY c.date DESC''', (selected_member,))
    else:
        c.execute('''SELECT m.name, c.amount, c.type, c.date
                     FROM contributions c 
                     JOIN members m ON c.member_id = m.id
                     ORDER BY c.date DESC''')
    all_contributions = c.fetchall()

    # Loans with repayments
    if selected_member:
        c.execute('''SELECT m.name, l.id, l.principal, l.interest_rate, l.repayment_period, l.issue_date,
                            IFNULL(SUM(r.amount_paid), 0)
                     FROM loans l
                     JOIN members m ON m.id = l.member_id
                     LEFT JOIN loan_repayments r ON l.id = r.loan_id
                     WHERE m.id = ?
                     GROUP BY l.id''', (selected_member,))
    else:
        c.execute('''SELECT m.name, l.id, l.principal, l.interest_rate, l.repayment_period, l.issue_date,
                            IFNULL(SUM(r.amount_paid), 0)
                     FROM loans l
                     JOIN members m ON m.id = l.member_id
                     LEFT JOIN loan_repayments r ON l.id = r.loan_id
                     GROUP BY l.id''')
    loans = c.fetchall()
    conn.close()

    # Process loans
    loan_data = []
    for name, loan_id, principal, rate, period, issue_date, repaid in loans:
        total_interest = principal * rate * period
        total_due = principal + total_interest
        balance = total_due - repaid
        loan_data.append((name, principal, total_due, repaid, balance, total_interest, issue_date, loan_id))

    # Pie Chart Data
    conn = sqlite3.connect('chama.db')
    c = conn.cursor()
    c.execute('''SELECT m.name, IFNULL(SUM(c.amount), 0)
                 FROM members m 
                 LEFT JOIN contributions c ON m.id = c.member_id
                 GROUP BY m.id''')
    members_summary = c.fetchall()
    conn.close()

    chart_labels = [row[0] for row in members_summary]
    chart_data = [row[1] for row in members_summary]

    return render_template("dashboard.html",
                           all_contributions=all_contributions,
                           loans=loan_data,
                           members=members,
                           chart_labels=chart_labels,
                           chart_data=chart_data,
                           selected_member=selected_member)


@app.route("/delete_loan/<int:loan_id>")
def delete_loan(loan_id):
    if not session.get('admin'):
        return redirect(url_for('login'))

    conn = sqlite3.connect('chama.db')
    c = conn.cursor()
    c.execute("DELETE FROM loan_repayments WHERE loan_id=?", (loan_id,))
    c.execute("DELETE FROM withdrawals WHERE loan_id=?", (loan_id,))
    c.execute("DELETE FROM loans WHERE id=?", (loan_id,))
    conn.commit()
    conn.close()
    flash("Loan deleted successfully.")
    return redirect(url_for('dashboard'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)), debug=True)
