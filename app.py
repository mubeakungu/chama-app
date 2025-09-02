from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, make_response, render_template_string
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func
from datetime import datetime
import pandas as pd
from xhtml2pdf import pisa
import os

app = Flask(__name__)
app.secret_key = 'supersecret'

# --- Database Config ---
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL", "sqlite:///chama.db")  # set in Render
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


# --- MODELS ---
class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(100), nullable=False)


class Member(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(50))
    email = db.Column(db.String(100))
    join_date = db.Column(db.Date, default=datetime.utcnow)
    status = db.Column(db.String(50), default="pending")
    contributions = db.relationship("Contribution", backref="member", cascade="all, delete")
    loans = db.relationship("Loan", backref="member", cascade="all, delete")


class Contribution(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("member.id", ondelete="CASCADE"))
    amount = db.Column(db.Float, nullable=False)
    type = db.Column(db.String(50))
    date = db.Column(db.DateTime, default=datetime.utcnow)


class Loan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("member.id", ondelete="CASCADE"))
    loan_type = db.Column(db.String(50))
    principal = db.Column(db.Float, nullable=False)
    interest_rate = db.Column(db.Float, nullable=False)
    repayment_period = db.Column(db.Integer, nullable=False)
    issue_date = db.Column(db.DateTime, default=datetime.utcnow)
    withdrawals = db.relationship("Withdrawal", backref="loan", cascade="all, delete")
    repayments = db.relationship("LoanRepayment", backref="loan", cascade="all, delete")


class Withdrawal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loan.id", ondelete="CASCADE"))
    amount = db.Column(db.Float, nullable=False)
    disbursed_date = db.Column(db.DateTime, default=datetime.utcnow)


class LoanRepayment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loan.id", ondelete="CASCADE"))
    amount_paid = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)


# --- Ensure DB and default admin ---
with app.app_context():
    db.create_all()
    if not Admin.query.filter_by(username="admin").first():
        admin = Admin(username="admin", password="pass123")
        db.session.add(admin)
        db.session.commit()


# --- ROUTES ---
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        admin = Admin.query.filter_by(username=username, password=password).first()
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

    members = Member.query.all()
    contributions = Contribution.query.join(Member).add_columns(
        Contribution.id, Member.name.label("member_name"), Contribution.type,
        Contribution.amount, Contribution.date
    ).order_by(Contribution.date.desc()).all()

    loans = Loan.query.join(Member).add_columns(
        Loan.id, Member.name.label("name"), Loan.principal,
        Loan.interest_rate, Loan.repayment_period, Loan.issue_date
    ).all()

    total_contributions = db.session.query(func.sum(Contribution.amount)).scalar() or 0

    # Chart data: contributions per member
    member_sums = db.session.query(Member.name, func.sum(Contribution.amount)).outerjoin(
        Contribution).group_by(Member.id).all()
    chart_labels = [m[0] for m in member_sums]
    chart_data = [m[1] or 0 for m in member_sums]

    return render_template("dashboard.html",
                           members=members,
                           contributions=contributions,
                           loans=loans,
                           chart_labels=chart_labels,
                           chart_data=chart_data,
                           total_contributions=total_contributions)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)


