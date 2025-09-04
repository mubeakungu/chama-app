# This is a self-contained Flask application that demonstrates how to
# correctly populate the dashboard with loan status information.

import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, make_response, render_template_string
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func
from datetime import datetime
import pandas as pd
from xhtml2pdf import pisa
import json

app = Flask(__name__)
app.secret_key = 'supersecret'

# --- Database Config ---
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL", "sqlite:///chama.db")
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
    id_number = db.Column(db.String(50))
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

    # --- Members ---
    members = Member.query.all()

    # --- Contributions ---
    contributions = Contribution.query.join(Member).add_columns(
        Contribution.id, Contribution.member_id,
        Member.name.label("member_name"), Contribution.type,
        Contribution.amount, Contribution.date
    ).order_by(Contribution.date.desc()).all()

    # --- Loans ---
    loans = Loan.query.join(Member).add_columns(
        Loan.id, Member.name.label("name"), Loan.principal,
        Loan.interest_rate, Loan.repayment_period, Loan.issue_date
    ).order_by(Loan.issue_date.desc()).all()

    # --- Totals ---
    total_contributions = db.session.query(func.sum(Contribution.amount)).scalar() or 0
    total_loans = db.session.query(func.sum(Loan.principal)).scalar() or 0
    total_repayments = db.session.query(func.sum(LoanRepayment.amount_paid)).scalar() or 0

    # Calculate total interests (simple interest assumption)
    total_interests = 0
    all_loans = Loan.query.all()
    for loan in all_loans:
        total_interests += loan.principal * (loan.interest_rate / 100)

    # --- Contributions per member ---
    member_contributions = db.session.query(
        Member.name,
        func.sum(Contribution.amount).label("total_contributions")
    ).outerjoin(Contribution).group_by(Member.id).all()

    # --- Loans per member ---
    member_loans = db.session.query(
        Member.name,
        func.sum(Loan.principal).label("total_loans")
    ).outerjoin(Loan).group_by(Member.id).all()

    # --- Prepare chart data ---
    chart_labels = [m[0] for m in member_contributions] if member_contributions else []
    contributions_data = [float(m[1] or 0) for m in member_contributions] if member_contributions else []
    chart_data = contributions_data
    
    loans_dict = dict(member_loans)
    loans_data = [loans_dict.get(m[0], 0) for m in member_contributions]

    # --- Loan status logic ---
    ongoing_loans, completed_loans = [], []
    for loan in all_loans:
        total_repaid = db.session.query(func.sum(LoanRepayment.amount_paid)).filter_by(loan_id=loan.id).scalar() or 0
        total_due = loan.principal + (loan.principal * (loan.interest_rate / 100))

        loan_info = {
            'member_name': loan.member.name,
            'principal': loan.principal,
            'interest': loan.principal * (loan.interest_rate / 100),
            'repaid': total_repaid,
            'balance': total_due - total_repaid,
        }

        if total_repaid >= total_due:
            completed_loans.append(loan_info)
        else:
            ongoing_loans.append(loan_info)

    # --- Pass context to template ---
    return render_template(
        "dashboard.html",
        members=members,
        contributions=contributions,
        loans=loans,
        # Totals
        total_contributions=total_contributions,
        total_loans=total_loans,
        total_repayments=total_repayments,
        total_interests=total_interests,
        # Charts
        chart_labels=json.dumps(chart_labels),
        chart_data=json.dumps(chart_data),
        contributions_data=json.dumps(contributions_data),
        loans_data=json.dumps(loans_data),
        # Loan status
        ongoing_loans=ongoing_loans,
        completed_loans=completed_loans
    )


@app.route('/add_member', methods=['GET', 'POST'])
def add_member():
    if not session.get('admin'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        email = request.form['email']
        
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
        date_str = request.form['date']
        
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
            new_contribution = Contribution(member_id=member_id, amount=amount, type=contribution_type, date=date)
            db.session.add(new_contribution)
            db.session.commit()
            flash('Contribution added successfully!', 'success')
            return redirect(url_for('dashboard'))
        except (ValueError, KeyError) as e:
            db.session.rollback()
            flash(f'An error occurred with the form data: {e}', 'danger')
            return redirect(url_for('add_contribution'))
        except Exception as e:
            db.session.rollback()
            flash(f'An unexpected error occurred: {e}', 'danger')
            return redirect(url_for('add_contribution'))
    
    members = Member.query.all()
    return render_template('add_contribution.html', members=members)


@app.route('/add_loan', methods=['GET', 'POST'])
def add_loan():
    if not session.get('admin'):
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        try:
            member_id = request.form['member_id']
            principal = request.form['principal']
            interest_rate = request.form['interest_rate']
            repayment_period = request.form['repayment_period']
            loan_type = request.form['loan_type']
            issue_date_str = request.form.get('issue_date')

            if issue_date_str:
                issue_date = datetime.strptime(issue_date_str, '%Y-%m-%d').date()
            else:
                issue_date = datetime.utcnow().date()
                
            new_loan = Loan(
                member_id=member_id,
                principal=principal,
                interest_rate=interest_rate,
                repayment_period=repayment_period,
                loan_type=loan_type,
                issue_date=issue_date
            )
            db.session.add(new_loan)
            db.session.commit()
            flash('Loan added successfully!', 'success')
            return redirect(url_for('dashboard'))
        except (ValueError, KeyError) as e:
            db.session.rollback()
            flash(f'An error occurred with the form data: {e}', 'danger')
            return redirect(url_for('add_loan'))
        except Exception as e:
            db.session.rollback()
            flash(f'An unexpected error occurred: {e}', 'danger')
            return redirect(url_for('add_loan'))

    members = Member.query.all()
    return render_template('add_loan.html', members=members)


@app.route('/manage_member')
def manage_member():
    if not session.get('admin'):
        return redirect(url_for('login'))

    members = Member.query.all()
    contributions = db.session.query(
        Contribution.id,
        Contribution.amount,
        Contribution.date,
        Contribution.type,
        Member.name.label("member_name")
    ).join(Member).order_by(Contribution.date.desc()).all()

    loans = db.session.query(
        Loan.id,
        Loan.principal,
        Loan.interest_rate,
        Loan.repayment_period,
        Loan.issue_date,
        Member.name.label("name")
    ).join(Member).order_by(Loan.issue_date.desc()).all()

    total_contributions = db.session.query(func.sum(Contribution.amount)).scalar() or 0
    total_loans = db.session.query(func.sum(Loan.principal)).scalar() or 0
    total_repayments = db.session.query(func.sum(LoanRepayment.amount_paid)).scalar() or 0
    total_withdrawals = db.session.query(func.sum(Withdrawal.amount)).scalar() or 0

    chart_labels = [m.name for m in members]
    chart_data = []
    for m in members:
        total = db.session.query(func.sum(Contribution.amount)) \
            .filter(Contribution.member_id == m.id).scalar() or 0
        chart_data.append(total)

    return render_template(
        'manage_member.html',
        members=members,
        contributions=contributions,
        loans=loans,
        total_contributions=total_contributions,
        total_loans=total_loans,
        total_repayments=total_repayments,
        total_withdrawals=total_withdrawals,
        chart_labels=chart_labels,
        chart_data=chart_data
    )


@app.route('/edit_member/<int:member_id>', methods=['GET', 'POST'])
def edit_member(member_id):
    if not session.get('admin'):
        return redirect(url_for('login'))
    
    member = Member.query.get_or_404(member_id)
    
    if request.method == 'POST':
        member.name = request.form['name']
        member.phone = request.form['phone']
        member.email = request.form['email']
        
        id_number_str = request.form.get('id_number')
        join_date_str = request.form.get('join_date')

        if id_number_str:
            member.id_number = id_number_str
        
        if join_date_str:
            try:
                member.join_date = datetime.strptime(join_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash("Invalid date format. Please use YYYY-MM-DD.", 'danger')
                return redirect(url_for('edit_member', member_id=member.id))
        
        try:
            db.session.commit()
            flash('Member updated successfully!', 'success')
            return redirect(url_for('manage_member'))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred: {e}', 'danger')
            return redirect(url_for('edit_member', member_id=member.id))
            
    return render_template('edit_member.html', member=member)


@app.route('/delete_member/<int:member_id>', methods=['POST'])
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


@app.route('/delete_contribution/<int:contribution_id>/<int:member_id>', methods=['POST'])
def delete_contribution(contribution_id, member_id):
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
        
    return redirect(url_for('member_summary', member_id=member_id))


@app.route('/delete_loan/<int:loan_id>', methods=['POST'])
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


@app.route('/repay_loan', methods=['GET', 'POST'])
def repay_loan():
    if not session.get('admin'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        loan_id = request.form['loan_id']
        amount_paid = request.form['amount_paid']
        
        try:
            new_repayment = LoanRepayment(loan_id=loan_id, amount_paid=amount_paid)
            db.session.add(new_repayment)
            db.session.commit()
            flash('Loan repayment recorded successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred: {e}', 'danger')
        return redirect(url_for('repay_loan'))
    
    loans = Loan.query.all()
    return render_template('repay_loan.html', loans=loans)


@app.route('/withdraw_loan', methods=['GET', 'POST'])
def withdraw_loan():
    if not session.get('admin'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        loan_id = request.form['loan_id']
        amount = request.form['amount']

        try:
            new_withdrawal = Withdrawal(loan_id=loan_id, amount=amount)
            db.session.add(new_withdrawal)
            db.session.commit()
            flash('Loan withdrawal recorded successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred: {e}', 'danger')
        return redirect(url_for('withdraw_loan'))
    
    loans = Loan.query.all()
    return render_template('withdraw_loan.html', loans=loans)


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

    data = {
        'members': members,
        'contributions': contributions,
        'loans': loans,
        'repayments': repayments,
        'generated_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    html_content = render_template('report_template.html', data=data)

    pdf_file = "chama_report.pdf"
    
    pisa_status = pisa.CreatePDF(
        html_content,
        dest=open(pdf_file, "wb"))
    
    if pisa_status.err:
        flash('An error occurred generating the PDF report.', 'danger')
        return redirect(url_for('dashboard'))
    
    return send_file(pdf_file, as_attachment=True, download_name="chama_report.pdf", mimetype='application/pdf')


@app.route('/member_summary/<int:member_id>')
def member_summary(member_id):
    if not session.get('admin'):
        return redirect(url_for('login'))

    member = Member.query.get_or_404(member_id)
    contributions = Contribution.query.filter_by(member_id=member.id).order_by(Contribution.date.desc()).all()
    loans = Loan.query.filter_by(member_id=member.id).order_by(Loan.issue_date.desc()).all()

    total_contributions = db.session.query(func.sum(Contribution.amount)).filter_by(member_id=member.id).scalar() or 0
    
    for loan in loans:
        total_repaid = db.session.query(func.sum(LoanRepayment.amount_paid)).filter_by(loan_id=loan.id).scalar() or 0
        loan.remaining_balance = loan.principal - total_repaid
        loan.total_repaid = total_repaid

    return render_template('member_summary.html',
                            member=member,
                            contributions=contributions,
                            loans=loans,
                            total_contributions=total_contributions)


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)
