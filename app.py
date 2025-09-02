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
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL", "sqlite:///chama.db") # set in Render
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
    repayments = db.relationship("LoanRepayment", backref="loan", cascade="all, delete")
    withdrawals = db.relationship("Withdrawal", backref="loan", cascade="all, delete")


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
            flash('Invalid credentials', 'danger')
            return redirect(url_for('login'))
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


@app.route('/add_member', methods=['GET', 'POST'])
def add_member():
    if not session.get('admin'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        email = request.form['email']
        
        # Simple validation
        if not name or not phone:
            flash('Name and phone number are required!', 'danger')
            return redirect(url_for('add_member'))

        try:
            new_member = Member(name=name, phone=phone, email=email)
            db.session.add(new_member)
            db.session.commit()
            flash('Member added successfully!', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred: {e}', 'danger')
            return redirect(url_for('add_member'))

    return render_template('add_member.html')


@app.route('/add_contribution', methods=['GET', 'POST'])
def add_contribution():
    if not session.get('admin'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        member_id = request.form['member_id']
        amount = request.form['amount']
        contribution_type = request.form['type']
        
        try:
            new_contribution = Contribution(member_id=member_id, amount=amount, type=contribution_type)
            db.session.add(new_contribution)
            db.session.commit()
            flash('Contribution added successfully!', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred: {e}', 'danger')
            return redirect(url_for('add_contribution'))
    
    members = Member.query.all()
    return render_template('add_contribution.html', members=members)


@app.route('/add_loan', methods=['GET', 'POST'])
def add_loan():
    if not session.get('admin'):
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        member_id = request.form['member_id']
        principal = request.form['principal']
        interest_rate = request.form['interest_rate']
        repayment_period = request.form['repayment_period']
        loan_type = request.form['loan_type']
        
        try:
            new_loan = Loan(
                member_id=member_id,
                principal=principal,
                interest_rate=interest_rate,
                repayment_period=repayment_period,
                loan_type=loan_type
            )
            db.session.add(new_loan)
            db.session.commit()
            flash('Loan added successfully!', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred: {e}', 'danger')
            return redirect(url_for('add_loan'))

    members = Member.query.all()
    return render_template('add_loan.html', members=members)


@app.route('/delete_member/<int:member_id>')
def delete_member(member_id):
    if not session.get('admin'):
        return redirect(url_for('login'))
        
    member_to_delete = Member.query.get_or_404(member_id)
    try:
        db.session.delete(member_to_delete)
        db.session.commit()
        flash('Member and all their data deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred: {e}', 'danger')
        
    return redirect(url_for('dashboard'))


@app.route('/delete_contribution/<int:contribution_id>')
def delete_contribution(contribution_id):
    if not session.get('admin'):
        return redirect(url_for('login'))
        
    contribution_to_delete = Contribution.query.get_or_404(contribution_id)
    try:
        db.session.delete(contribution_to_delete)
        db.session.commit()
        flash('Contribution deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred: {e}', 'danger')
        
    return redirect(url_for('dashboard'))


@app.route('/delete_loan/<int:loan_id>')
def delete_loan(loan_id):
    if not session.get('admin'):
        return redirect(url_for('login'))
        
    loan_to_delete = Loan.query.get_or_404(loan_id)
    try:
        db.session.delete(loan_to_delete)
        db.session.commit()
        flash('Loan and all its data deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred: {e}', 'danger')
        
    return redirect(url_for('dashboard'))


@app.route('/loan_details/<int:loan_id>', methods=['GET', 'POST'])
def loan_details(loan_id):
    if not session.get('admin'):
        return redirect(url_for('login'))
        
    loan = Loan.query.get_or_404(loan_id)
    
    if request.method == 'POST':
        amount_paid = request.form['amount_paid']
        try:
            new_repayment = LoanRepayment(loan_id=loan.id, amount_paid=amount_paid)
            db.session.add(new_repayment)
            db.session.commit()
            flash('Repayment recorded successfully!', 'success')
            return redirect(url_for('loan_details', loan_id=loan.id))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred: {e}', 'danger')
            return redirect(url_for('loan_details', loan_id=loan.id))

    total_repaid = db.session.query(func.sum(LoanRepayment.amount_paid)).filter_by(loan_id=loan.id).scalar() or 0
    remaining_balance = loan.principal - total_repaid
    repayments = LoanRepayment.query.filter_by(loan_id=loan.id).order_by(LoanRepayment.payment_date.desc()).all()
    
    return render_template('loan_details.html', loan=loan, total_repaid=total_repaid, remaining_balance=remaining_balance, repayments=repayments)


@app.route('/generate_report')
def generate_report():
    if not session.get('admin'):
        return redirect(url_for('login'))

    members = Member.query.all()
    contributions = Contribution.query.join(Member).all()
    loans = Loan.query.join(Member).all()
    repayments = LoanRepayment.query.join(Loan).all()

    # Compile data into a dictionary for the template
    data = {
        'members': members,
        'contributions': contributions,
        'loans': loans,
        'repayments': repayments,
        'generated_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    # Render HTML template for the report
    html_content = render_template('report_template.html', data=data)

    # Convert HTML to PDF
    pdf_file = "chama_report.pdf"
    
    pisa_status = pisa.CreatePDF(
        html_content,
        dest=open(pdf_file, "wb"))
    
    if pisa_status.err:
        flash('An error occurred generating the PDF report.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Send the PDF file
    return send_file(pdf_file, as_attachment=True, download_name="chama_report.pdf", mimetype='application/pdf')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)
    


