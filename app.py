"""
PCG Hobor Church Financial Reporting App
A Flask web application for managing church finances with approval workflow
"""

import os
import json
from datetime import datetime, date
from functools import wraps

from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, send_file, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, DecimalField, TextAreaField, DateField, HiddenField, BooleanField
from wtforms.validators import DataRequired, NumberRange, Optional, Length
from werkzeug.security import generate_password_hash, check_password_hash
from passlib.hash import pbkdf2_sha256
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'pcg-hobor-secret-key-change-in-production-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pcg_hobor_finance.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

# ============== Database Models ==============

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'admin' or 'treasurer'
    is_active_flag = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = pbkdf2_sha256.hash(password)
    
    def check_password(self, password):
        return pbkdf2_sha256.verify(password, self.password_hash)


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category_type = db.Column(db.String(20), nullable=False)  # 'income' or 'expenditure'
    is_active = db.Column(db.Boolean, default=True)
    
    @staticmethod
    def get_default_categories():
        return [
            {'name': 'Offertory', 'category_type': 'income'},
            {'name': 'Tithe', 'category_type': 'income'},
            {'name': 'Thanksgiving', 'category_type': 'income'},
            {'name': 'Donations', 'category_type': 'income'},
            {'name': 'Harvest', 'category_type': 'income'},
            {'name': 'Momo Transfer In', 'category_type': 'income'},
            {'name': 'Other Income', 'category_type': 'income'},
            {'name': 'Utilities', 'category_type': 'expenditure'},
            {'name': 'Stationery', 'category_type': 'expenditure'},
            {'name': 'Transport', 'category_type': 'expenditure'},
            {'name': 'Welfare', 'category_type': 'expenditure'},
            {'name': 'Momo Transfer Out', 'category_type': 'expenditure'},
            {'name': 'Maintenance', 'category_type': 'expenditure'},
            {'name': 'Programs', 'category_type': 'expenditure'},
            {'name': 'Other Expenditure', 'category_type': 'expenditure'},
        ]


class SessionReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_date = db.Column(db.Date, nullable=False, unique=True)
    balance_bf_momo = db.Column(db.Float, default=0.0)
    balance_bf_bank = db.Column(db.Float, default=0.0)
    balance_bf_cash = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='draft')  # draft, submitted, approved, rejected
    submitted_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    submitted_at = db.Column(db.DateTime)
    approved_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    approved_at = db.Column(db.DateTime)
    rejection_reason = db.Column(db.Text)
    admin_comments = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    submitted_by = db.relationship('User', foreign_keys=[submitted_by_id], backref='submitted_reports')
    approved_by = db.relationship('User', foreign_keys=[approved_by_id], backref='approved_reports')
    
    @property
    def income_transactions(self):
        return Transaction.query.filter_by(session_id=self.id, transaction_type='income').all()
    
    @property
    def expenditure_transactions(self):
        return Transaction.query.filter_by(session_id=self.id, transaction_type='expenditure').all()
    
    def calculate_closing_balances(self):
        """Calculate closing balances for each fund"""
        income_momo = sum(t.amount for t in self.income_transactions if t.fund == 'momo')
        income_bank = sum(t.amount for t in self.income_transactions if t.fund == 'bank')
        income_cash = sum(t.amount for t in self.income_transactions if t.fund == 'cash')
        
        expenditure_momo = sum(t.amount for t in self.expenditure_transactions if t.fund == 'momo')
        expenditure_bank = sum(t.amount for t in self.expenditure_transactions if t.fund == 'bank')
        expenditure_cash = sum(t.amount for t in self.expenditure_transactions if t.fund == 'cash')
        
        cd_momo = self.balance_bf_momo + income_momo - expenditure_momo
        cd_bank = self.balance_bf_bank + income_bank - expenditure_bank
        cd_cash = self.balance_bf_cash + income_cash - expenditure_cash
        
        return {
            'momo': round(cd_momo, 2),
            'bank': round(cd_bank, 2),
            'cash': round(cd_cash, 2)
        }
    
    def get_net_position(self):
        total_income = sum(t.amount for t in self.income_transactions)
        total_expenditure = sum(t.amount for t in self.expenditure_transactions)
        return round(total_income - total_expenditure, 2)


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('session_report.id'), nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False)  # 'income' or 'expenditure'
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    description = db.Column(db.String(500))
    amount = db.Column(db.Float, nullable=False)
    fund = db.Column(db.String(20), nullable=False)  # 'momo', 'bank', 'cash'
    entered_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    session = db.relationship('SessionReport', backref='transactions')
    category = db.relationship('Category', backref='transactions')
    entered_by = db.relationship('User', backref='entered_transactions')


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    action = db.Column(db.String(50), nullable=False)
    entity_type = db.Column(db.String(50))
    entity_id = db.Column(db.Integer)
    details = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='audit_logs')


class Member(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    education_level = db.Column(db.String(50), nullable=False, default='None')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @staticmethod
    def get_valid_education_levels():
        return ['None', 'Primary', 'JHS', 'SHS', 'TVET', 'Tertiary', 'Postgraduate']


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ============== Forms ==============

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])


class UserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=4)])
    full_name = StringField('Full Name', validators=[DataRequired()])
    role = SelectField('Role', choices=[('treasurer', 'Treasurer'), ('admin', 'Admin')], validators=[DataRequired()])
    is_active_flag = BooleanField('Active')


class CategoryForm(FlaskForm):
    name = StringField('Category Name', validators=[DataRequired()])
    category_type = SelectField('Type', choices=[('income', 'Income'), ('expenditure', 'Expenditure')], validators=[DataRequired()])
    is_active = BooleanField('Active')


class TransactionForm(FlaskForm):
    transaction_type = SelectField('Type', choices=[('income', 'Income'), ('expenditure', 'Expenditure')], validators=[DataRequired()])
    category_id = SelectField('Category', coerce=int, validators=[DataRequired()])
    description = StringField('Description', validators=[Optional()])
    amount = DecimalField('Amount (GHS)', validators=[DataRequired(), NumberRange(min=0.01)])
    fund = SelectField('Fund', choices=[('momo', 'Mobile Money'), ('bank', 'Bank'), ('cash', 'Cash')], validators=[DataRequired()])


class SessionReportForm(FlaskForm):
    session_date = DateField('Session Date', format='%Y-%m-%d', validators=[DataRequired()])
    balance_bf_momo = DecimalField('Balance B/F - Mobile Money', validators=[DataRequired(), NumberRange(min=0)])
    balance_bf_bank = DecimalField('Balance B/F - Bank', validators=[DataRequired(), NumberRange(min=0)])
    balance_bf_cash = DecimalField('Balance B/F - Cash', validators=[DataRequired(), NumberRange(min=0)])


class RejectionForm(FlaskForm):
    rejection_reason = TextAreaField('Reason for Rejection', validators=[DataRequired()])


class AdminCommentsForm(FlaskForm):
    admin_comments = TextAreaField('Admin Comments')


class MemberForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(max=120)])
    phone = StringField('Phone', validators=[Optional(), Length(max=20)])
    email = StringField('Email', validators=[Optional(), Length(max=120)])
    education_level = SelectField('Education Level', 
                                  choices=[(level, level) for level in Member.get_valid_education_levels()],
                                  validators=[DataRequired()])


# ============== Helper Functions ==============

def log_audit(action, entity_type, entity_id, details=None):
    """Log an audit trail entry"""
    if current_user.is_authenticated:
        audit = AuditLog(
            user_id=current_user.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=json.dumps(details) if details else None
        )
        db.session.add(audit)
        db.session.commit()


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Admin access required.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def get_previous_session(session_date):
    """Get the previous session before the given date"""
    return SessionReport.query.filter(
        SessionReport.session_date < session_date,
        SessionReport.status == 'approved'
    ).order_by(SessionReport.session_date.desc()).first()


def initialize_default_data():
    """Initialize database with default categories and admin user"""
    # Create default categories
    if Category.query.count() == 0:
        for cat in Category.get_default_categories():
            category = Category(name=cat['name'], category_type=cat['category_type'])
            db.session.add(category)
        db.session.commit()
    
    # Create default admin user if none exists
    if User.query.filter_by(role='admin').count() == 0:
        admin = User(
            username='admin',
            full_name='Catechist Admin',
            role='admin',
            is_active_flag=True
        )
        admin.set_password('admin123')  # Default password - should be changed
        db.session.add(admin)
        db.session.commit()
        print("Default admin created: username='admin', password='admin123'")


def migrate_add_education_level():
    """Migration script to add education_level column to members table if not exists"""
    from sqlalchemy import inspect
    
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    
    if 'member' in tables:
        columns = [col['name'] for col in inspector.get_columns('member')]
        if 'education_level' not in columns:
            with db.engine.connect() as conn:
                conn.execute(db.text("""
                    ALTER TABLE member ADD COLUMN education_level VARCHAR(50) DEFAULT 'None' NOT NULL
                """))
                conn.commit()
            print("Migration: Added education_level column to member table")
        else:
            print("Migration: education_level column already exists in member table")
    # Table doesn't exist yet - will be created with the column on first run


# ============== Routes ==============

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data) and user.is_active_flag:
            login_user(user)
            next_page = request.args.get('next')
            flash(f'Welcome back, {user.full_name}!', 'success')
            return redirect(next_page or url_for('dashboard'))
        flash('Invalid username or password, or account is inactive.', 'error')
    
    return render_template('login.html', form=form)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    # Get pending submissions for admin
    pending_reports = []
    if current_user.role == 'admin':
        pending_reports = SessionReport.query.filter_by(status='submitted').order_by(SessionReport.session_date.desc()).all()
    
    # Get recent activity
    recent_activity = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(10).all()
    
    # Get current balances from latest approved session
    latest_session = SessionReport.query.filter_by(status='approved').order_by(SessionReport.session_date.desc()).first()
    current_balances = {'momo': 0, 'bank': 0, 'cash': 0}
    if latest_session:
        current_balances = latest_session.calculate_closing_balances()
    
    # Get user's recent reports
    if current_user.role == 'admin':
        user_reports = SessionReport.query.order_by(SessionReport.session_date.desc()).limit(5).all()
    else:
        user_reports = SessionReport.query.filter_by(submitted_by_id=current_user.id).order_by(SessionReport.session_date.desc()).limit(5).all()
    
    return render_template('dashboard.html', 
                         pending_reports=pending_reports,
                         recent_activity=recent_activity,
                         current_balances=current_balances,
                         user_reports=user_reports)


@app.route('/sessions')
@login_required
def sessions_list():
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', 'all')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    query = SessionReport.query
    
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    if date_from:
        query = query.filter(SessionReport.session_date >= datetime.strptime(date_from, '%Y-%m-%d').date())
    
    if date_to:
        query = query.filter(SessionReport.session_date <= datetime.strptime(date_to, '%Y-%m-%d').date())
    
    if current_user.role != 'admin':
        query = query.filter_by(submitted_by_id=current_user.id)
    
    sessions = query.order_by(SessionReport.session_date.desc()).paginate(page=page, per_page=20)
    
    return render_template('sessions_list.html', sessions=sessions, status_filter=status_filter, date_from=date_from, date_to=date_to)


@app.route('/session/new', methods=['GET', 'POST'])
@login_required
def new_session():
    form = SessionReportForm()
    
    # Pre-fill with previous session's closing balances if available
    if request.method == 'GET':
        prev_session = get_previous_session(date.today())
        if prev_session:
            closing = prev_session.calculate_closing_balances()
            form.balance_bf_momo.data = closing['momo']
            form.balance_bf_bank.data = closing['bank']
            form.balance_bf_cash.data = closing['cash']
    
    if form.validate_on_submit():
        # Check if session for this date already exists
        existing = SessionReport.query.filter_by(session_date=form.session_date.data).first()
        if existing:
            flash('A session for this date already exists.', 'error')
            return redirect(url_for('new_session'))
        
        session_report = SessionReport(
            session_date=form.session_date.data,
            balance_bf_momo=float(form.balance_bf_momo.data),
            balance_bf_bank=float(form.balance_bf_bank.data),
            balance_bf_cash=float(form.balance_bf_cash.data),
            submitted_by_id=current_user.id
        )
        db.session.add(session_report)
        db.session.commit()
        
        log_audit('create_session', 'SessionReport', session_report.id, 
                 {'date': str(form.session_date.data)})
        
        flash('Session created. Now add transactions.', 'success')
        return redirect(url_for('edit_session', session_id=session_report.id))
    
    return render_template('session_form.html', form=form, transactions=[], session_report=None)


@app.route('/session/<int:session_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_session(session_id):
    session_report = SessionReport.query.get_or_404(session_id)
    
    # Check permissions
    if current_user.role != 'admin' and session_report.submitted_by_id != current_user.id:
        flash('You do not have permission to edit this session.', 'error')
        return redirect(url_for('sessions_list'))
    
    if session_report.status == 'approved':
        flash('Approved sessions cannot be edited. Contact admin if changes are needed.', 'error')
        return redirect(url_for('view_session', session_id=session_id))
    
    form = SessionReportForm(obj=session_report)
    transactions = session_report.transactions
    
    if form.validate_on_submit():
        session_report.session_date = form.session_date.data
        session_report.balance_bf_momo = float(form.balance_bf_momo.data)
        session_report.balance_bf_bank = float(form.balance_bf_bank.data)
        session_report.balance_bf_cash = float(form.balance_bf_cash.data)
        session_report.updated_at = datetime.utcnow()
        
        db.session.commit()
        log_audit('update_session', 'SessionReport', session_report.id,
                 {'balances_updated': True})
        
        flash('Session updated successfully.', 'success')
        return redirect(url_for('edit_session', session_id=session_id))
    
    # Get categories for the template
    categories = Category.query.filter_by(is_active=True).all()
    
    return render_template('session_form.html', form=form, transactions=transactions, 
                          session_report=session_report, categories=categories)


@app.route('/session/<int:session_id>/add-transaction', methods=['POST'])
@login_required
def add_transaction(session_id):
    session_report = SessionReport.query.get_or_404(session_id)
    
    if session_report.status == 'approved':
        return jsonify({'success': False, 'message': 'Cannot add transactions to approved session'}), 400
    
    form = TransactionForm()
    if form.validate_on_submit():
        transaction = Transaction(
            session_id=session_id,
            transaction_type=form.transaction_type.data,
            category_id=form.category_id.data,
            description=form.description.data,
            amount=float(form.amount.data),
            fund=form.fund.data,
            entered_by_id=current_user.id
        )
        db.session.add(transaction)
        db.session.commit()
        
        log_audit('add_transaction', 'Transaction', transaction.id,
                 {'type': form.transaction_type.data, 'amount': form.amount.data})
        
        return jsonify({'success': True, 'message': 'Transaction added'})
    
    return jsonify({'success': False, 'message': 'Invalid form data'}), 400


@app.route('/session/<int:session_id>/delete-transaction/<int:transaction_id>', methods=['POST'])
@login_required
def delete_transaction(session_id, transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    session_report = SessionReport.query.get_or_404(session_id)
    
    if session_report.status == 'approved':
        return jsonify({'success': False, 'message': 'Cannot modify approved session'}), 400
    
    db.session.delete(transaction)
    db.session.commit()
    
    log_audit('delete_transaction', 'Transaction', transaction_id, {})
    
    return jsonify({'success': True, 'message': 'Transaction deleted'})


@app.route('/session/<int:session_id>')
@login_required
def view_session(session_id):
    session_report = SessionReport.query.get_or_404(session_id)
    return render_template('session_view.html', session_report=session_report)


@app.route('/session/<int:session_id>/submit', methods=['POST'])
@login_required
def submit_session(session_id):
    session_report = SessionReport.query.get_or_404(session_id)
    
    if current_user.role != 'admin' and session_report.submitted_by_id != current_user.id:
        flash('You can only submit your own sessions.', 'error')
        return redirect(url_for('sessions_list'))
    
    if session_report.status == 'approved':
        flash('This session is already approved.', 'error')
        return redirect(url_for('view_session', session_id=session_id))
    
    session_report.status = 'submitted'
    session_report.submitted_at = datetime.utcnow()
    db.session.commit()
    
    log_audit('submit_session', 'SessionReport', session_id, {})
    
    flash('Session submitted for approval.', 'success')
    return redirect(url_for('view_session', session_id=session_id))


@app.route('/session/<int:session_id>/approve', methods=['POST'])
@login_required
@admin_required
def approve_session(session_id):
    session_report = SessionReport.query.get_or_404(session_id)
    
    if session_report.status != 'submitted':
        flash('Only submitted sessions can be approved.', 'error')
        return redirect(url_for('view_session', session_id=session_id))
    
    session_report.status = 'approved'
    session_report.approved_by_id = current_user.id
    session_report.approved_at = datetime.utcnow()
    session_report.rejection_reason = None
    db.session.commit()
    
    log_audit('approve_session', 'SessionReport', session_id, {})
    
    flash('Session approved successfully.', 'success')
    return redirect(url_for('view_session', session_id=session_id))


@app.route('/session/<int:session_id>/reject', methods=['GET', 'POST'])
@login_required
@admin_required
def reject_session(session_id):
    session_report = SessionReport.query.get_or_404(session_id)
    form = RejectionForm()
    
    if form.validate_on_submit():
        session_report.status = 'rejected'
        session_report.rejection_reason = form.rejection_reason.data
        db.session.commit()
        
        log_audit('reject_session', 'SessionReport', session_id,
                 {'reason': form.rejection_reason.data})
        
        flash('Session rejected and sent back.', 'warning')
        return redirect(url_for('view_session', session_id=session_id))
    
    return render_template('reject_session.html', form=form, session_report=session_report)


@app.route('/session/<int:session_id>/reopen', methods=['POST'])
@login_required
@admin_required
def reopen_session(session_id):
    session_report = SessionReport.query.get_or_404(session_id)
    
    session_report.status = 'draft'
    session_report.approved_by_id = None
    session_report.approved_at = None
    session_report.rejection_reason = None
    db.session.commit()
    
    log_audit('reopen_session', 'SessionReport', session_id, {})
    
    flash('Session reopened for editing.', 'info')
    return redirect(url_for('edit_session', session_id=session_id))


@app.route('/session/<int:session_id>/pdf')
@login_required
def export_session_pdf(session_id):
    session_report = SessionReport.query.get_or_404(session_id)
    
    # Create PDF
    filename = f"PCG_Hobor_Report_{session_report.session_date.strftime('%Y-%m-%d')}.pdf"
    doc = SimpleDocTemplate(filename, pagesize=landscape(A4))
    elements = []
    styles = getSampleStyleSheet()
    
    # Title style
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        alignment=TA_CENTER,
        spaceAfter=12
    )
    
    # Header
    elements.append(Paragraph("PRESBYTERIAN CHURCH OF GHANA, HOBOR", title_style))
    elements.append(Paragraph("FINANCIAL REPORT", title_style))
    elements.append(Paragraph(f"Date: {session_report.session_date.strftime('%A, %B %d, %Y')}", 
                             ParagraphStyle('DateStyle', parent=styles['Normal'], alignment=TA_CENTER)))
    elements.append(Spacer(1, 0.3*inch))
    
    # Opening Balances
    elements.append(Paragraph("OPENING BALANCES (Brought Forward)", styles['Heading2']))
    opening_data = [
        ['Fund', 'Amount (GHS)'],
        ['Mobile Money', f"{session_report.balance_bf_momo:,.2f}"],
        ['Bank', f"{session_report.balance_bf_bank:,.2f}"],
        ['Cash', f"{session_report.balance_bf_cash:,.2f}"],
        ['TOTAL', f"{session_report.balance_bf_momo + session_report.balance_bf_bank + session_report.balance_bf_cash:,.2f}"]
    ]
    opening_table = Table(opening_data, colWidths=[3*inch, 2*inch])
    opening_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(opening_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Income Transactions
    elements.append(Paragraph("INCOME TRANSACTIONS", styles['Heading2']))
    income_data = [['Category', 'Description', 'Fund', 'Amount (GHS)']]
    total_income = 0
    for t in session_report.income_transactions:
        income_data.append([
            t.category.name,
            t.description or '-',
            t.fund.upper(),
            f"{t.amount:,.2f}"
        ])
        total_income += t.amount
    income_data.append(['', '', 'TOTAL INCOME', f"{total_income:,.2f}"])
    
    income_table = Table(income_data, colWidths=[2*inch, 2.5*inch, 1.5*inch, 1.5*inch])
    income_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgreen),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('BACKGROUND', (0, -1), (-1, -1), colors.palegreen),
    ]))
    elements.append(income_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Expenditure Transactions
    elements.append(Paragraph("EXPENDITURE TRANSACTIONS", styles['Heading2']))
    expenditure_data = [['Category', 'Description', 'Fund', 'Amount (GHS)']]
    total_expenditure = 0
    for t in session_report.expenditure_transactions:
        expenditure_data.append([
            t.category.name,
            t.description or '-',
            t.fund.upper(),
            f"{t.amount:,.2f}"
        ])
        total_expenditure += t.amount
    expenditure_data.append(['', '', 'TOTAL EXPENDITURE', f"{total_expenditure:,.2f}"])
    
    expenditure_table = Table(expenditure_data, colWidths=[2*inch, 2.5*inch, 1.5*inch, 1.5*inch])
    expenditure_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightcoral),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('BACKGROUND', (0, -1), (-1, -1), colors.salmon),
    ]))
    elements.append(expenditure_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Closing Balances
    closing = session_report.calculate_closing_balances()
    elements.append(Paragraph("CLOSING BALANCES (Carried Down)", styles['Heading2']))
    closing_data = [
        ['Fund', 'Amount (GHS)'],
        ['Mobile Money', f"{closing['momo']:,.2f}"],
        ['Bank', f"{closing['bank']:,.2f}"],
        ['Cash', f"{closing['cash']:,.2f}"],
        ['TOTAL', f"{closing['momo'] + closing['bank'] + closing['cash']:,.2f}"]
    ]
    closing_table = Table(closing_data, colWidths=[3*inch, 2*inch])
    closing_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(closing_table)
    elements.append(Spacer(1, 0.5*inch))
    
    # Net Position
    net = session_report.get_net_position()
    net_color = colors.green if net >= 0 else colors.red
    elements.append(Paragraph(f"NET POSITION FOR THE DAY: GHS {net:,.2f}", 
                             ParagraphStyle('NetStyle', parent=styles['Heading2'], textColor=net_color)))
    elements.append(Spacer(1, 0.5*inch))
    
    # Status
    status_text = f"Status: {session_report.status.upper()}"
    if session_report.approved_at:
        status_text += f" (Approved by {session_report.approved_by.full_name} on {session_report.approved_at.strftime('%Y-%m-%d %H:%M')})"
    elements.append(Paragraph(status_text, styles['Normal']))
    elements.append(Spacer(1, 0.5*inch))
    
    # Signature lines
    elements.append(Spacer(1, 0.5*inch))
    sig_table = Table([
        ['_________________________', '_________________________'],
        ['Treasurer', 'Catechist/Admin'],
        ['Date: _______________', 'Date: _______________']
    ], colWidths=[3*inch, 3*inch])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(sig_table)
    
    doc.build(elements)
    
    return send_file(filename, as_attachment=True)


@app.route('/reports/summary')
@login_required
def summary_report():
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    query = SessionReport.query.filter_by(status='approved')
    
    if date_from:
        query = query.filter(SessionReport.session_date >= datetime.strptime(date_from, '%Y-%m-%d').date())
    if date_to:
        query = query.filter(SessionReport.session_date <= datetime.strptime(date_to, '%Y-%m-%d').date())
    
    sessions = query.order_by(SessionReport.session_date).all()
    
    # Calculate period totals
    total_income = 0
    total_expenditure = 0
    income_by_category = {}
    expenditure_by_category = {}
    
    for s in sessions:
        for t in s.income_transactions:
            total_income += t.amount
            income_by_category[t.category.name] = income_by_category.get(t.category.name, 0) + t.amount
        for t in s.expenditure_transactions:
            total_expenditure += t.amount
            expenditure_by_category[t.category.name] = expenditure_by_category.get(t.category.name, 0) + t.amount
    
    # Opening and closing balances for period
    opening_balances = {'momo': 0, 'bank': 0, 'cash': 0}
    closing_balances = {'momo': 0, 'bank': 0, 'cash': 0}
    
    if sessions:
        # Opening = first session's B/F
        first_session = sessions[0]
        opening_balances = {
            'momo': first_session.balance_bf_momo,
            'bank': first_session.balance_bf_bank,
            'cash': first_session.balance_bf_cash
        }
        # Closing = last session's C/D
        last_session = sessions[-1]
        closing_balances = last_session.calculate_closing_balances()
    
    return render_template('summary_report.html', 
                         sessions=sessions,
                         total_income=total_income,
                         total_expenditure=total_expenditure,
                         income_by_category=income_by_category,
                         expenditure_by_category=expenditure_by_category,
                         opening_balances=opening_balances,
                         closing_balances=closing_balances,
                         date_from=date_from,
                         date_to=date_to)


@app.route('/users')
@login_required
@admin_required
def users_list():
    users = User.query.order_by(User.username).all()
    return render_template('users_list.html', users=users)


@app.route('/user/new', methods=['GET', 'POST'])
@login_required
@admin_required
def new_user():
    form = UserForm()
    if form.validate_on_submit():
        # Check if username exists
        if User.query.filter_by(username=form.username.data).first():
            flash('Username already exists.', 'error')
            return redirect(url_for('new_user'))
        
        user = User(
            username=form.username.data,
            full_name=form.full_name.data,
            role=form.role.data,
            is_active_flag=form.is_active_flag.data
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        
        log_audit('create_user', 'User', user.id, {'username': form.username.data})
        
        flash('User created successfully.', 'success')
        return redirect(url_for('users_list'))
    
    return render_template('user_form.html', form=form)


@app.route('/user/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    form = UserForm(obj=user)
    
    if form.validate_on_submit():
        user.full_name = form.full_name.data
        user.role = form.role.data
        user.is_active_flag = form.is_active_flag.data
        
        if form.password.data:
            user.set_password(form.password.data)
        
        db.session.commit()
        log_audit('update_user', 'User', user_id, {})
        
        flash('User updated successfully.', 'success')
        return redirect(url_for('users_list'))
    
    form.password.data = ''  # Don't show password
    return render_template('user_form.html', form=form, user=user)


@app.route('/categories')
@login_required
@admin_required
def categories_list():
    categories = Category.query.order_by(Category.category_type, Category.name).all()
    return render_template('categories_list.html', categories=categories)


@app.route('/category/new', methods=['GET', 'POST'])
@login_required
@admin_required
def new_category():
    form = CategoryForm()
    if form.validate_on_submit():
        category = Category(
            name=form.name.data,
            category_type=form.category_type.data,
            is_active=form.is_active.data
        )
        db.session.add(category)
        db.session.commit()
        
        log_audit('create_category', 'Category', category.id, {'name': form.name.data})
        
        flash('Category created successfully.', 'success')
        return redirect(url_for('categories_list'))
    
    return render_template('category_form.html', form=form)


@app.route('/category/<int:category_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_category(category_id):
    category = Category.query.get_or_404(category_id)
    form = CategoryForm(obj=category)
    
    if form.validate_on_submit():
        category.name = form.name.data
        category.category_type = form.category_type.data
        category.is_active = form.is_active.data
        db.session.commit()
        
        log_audit('update_category', 'Category', category_id, {})
        
        flash('Category updated successfully.', 'success')
        return redirect(url_for('categories_list'))
    
    return render_template('category_form.html', form=form, category=category)


@app.route('/audit-log')
@login_required
@admin_required
def audit_log():
    page = request.args.get('page', 1, type=int)
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).paginate(page=page, per_page=50)
    return render_template('audit_log.html', logs=logs)


# ============== Members API Routes ==============

@app.route('/api/members', methods=['GET'])
@login_required
def get_members():
    """Get all members with education level breakdown"""
    members = Member.query.all()
    result = []
    for m in members:
        result.append({
            'id': m.id,
            'name': m.name,
            'phone': m.phone,
            'email': m.email,
            'education_level': m.education_level,
            'created_at': m.created_at.isoformat() if m.created_at else None,
            'updated_at': m.updated_at.isoformat() if m.updated_at else None
        })
    return jsonify({'members': result})


@app.route('/api/members/<int:member_id>', methods=['GET'])
@login_required
def get_member(member_id):
    """Get a single member by ID"""
    member = Member.query.get_or_404(member_id)
    return jsonify({
        'id': member.id,
        'name': member.name,
        'phone': member.phone,
        'email': member.email,
        'education_level': member.education_level,
        'created_at': member.created_at.isoformat() if member.created_at else None,
        'updated_at': member.updated_at.isoformat() if member.updated_at else None
    })


@app.route('/api/members', methods=['POST'])
@login_required
def create_member():
    """Create a new member with education level validation"""
    data = request.get_json()
    
    if not data:
        return jsonify({'success': False, 'message': 'No data provided'}), 400
    
    name = data.get('name')
    phone = data.get('phone', '')
    email = data.get('email', '')
    education_level = data.get('education_level', 'None')
    
    # Validate required fields
    if not name:
        return jsonify({'success': False, 'message': 'Name is required'}), 400
    
    # Validate education_level against allowed values
    valid_levels = Member.get_valid_education_levels()
    if education_level not in valid_levels:
        return jsonify({
            'success': False, 
            'message': f"Invalid education_level. Must be one of: {', '.join(valid_levels)}"
        }), 400
    
    member = Member(
        name=name,
        phone=phone,
        email=email,
        education_level=education_level
    )
    db.session.add(member)
    db.session.commit()
    
    log_audit('create', 'member', member.id, {'name': name, 'education_level': education_level})
    
    return jsonify({
        'success': True,
        'message': 'Member created successfully',
        'member': {
            'id': member.id,
            'name': member.name,
            'phone': member.phone,
            'email': member.email,
            'education_level': member.education_level
        }
    }), 201


@app.route('/api/members/<int:member_id>', methods=['PUT'])
@login_required
def update_member(member_id):
    """Update a member with education level validation"""
    member = Member.query.get_or_404(member_id)
    data = request.get_json()
    
    if not data:
        return jsonify({'success': False, 'message': 'No data provided'}), 400
    
    # Update name if provided
    if 'name' in data:
        member.name = data['name']
    
    # Update phone if provided
    if 'phone' in data:
        member.phone = data['phone']
    
    # Update email if provided
    if 'email' in data:
        member.email = data['email']
    
    # Update education_level if provided, with validation
    if 'education_level' in data:
        education_level = data['education_level']
        valid_levels = Member.get_valid_education_levels()
        if education_level not in valid_levels:
            return jsonify({
                'success': False,
                'message': f"Invalid education_level. Must be one of: {', '.join(valid_levels)}"
            }), 400
        member.education_level = education_level
    
    db.session.commit()
    
    log_audit('update', 'member', member.id, {'education_level': member.education_level})
    
    return jsonify({
        'success': True,
        'message': 'Member updated successfully',
        'member': {
            'id': member.id,
            'name': member.name,
            'phone': member.phone,
            'email': member.email,
            'education_level': member.education_level
        }
    })


@app.route('/api/dashboard', methods=['GET'])
@login_required
def api_dashboard():
    """Get dashboard data including education level breakdown"""
    # Get current balances from latest approved session
    latest_session = SessionReport.query.filter_by(status='approved').order_by(SessionReport.session_date.desc()).first()
    current_balances = {'momo': 0, 'bank': 0, 'cash': 0}
    if latest_session:
        current_balances = latest_session.calculate_closing_balances()
    
    # Get pending submissions count (for admin)
    pending_count = 0
    if current_user.role == 'admin':
        pending_count = SessionReport.query.filter_by(status='submitted').count()
    
    # Get education level breakdown
    education_breakdown = {}
    for level in Member.get_valid_education_levels():
        count = Member.query.filter_by(education_level=level).count()
        if count > 0:
            education_breakdown[level] = count
    
    # Get total members count
    total_members = Member.query.count()
    
    return jsonify({
        'current_balances': current_balances,
        'pending_submissions': pending_count,
        'total_members': total_members,
        'byEducation': education_breakdown
    })


# ============== Template Rendering ==============

@app.template_filter('format_currency')
def format_currency(value):
    return f"GHS {value:,.2f}"


@app.template_filter('format_datetime')
def format_datetime(dt):
    if dt:
        return dt.strftime('%Y-%m-%d %H:%M')
    return '-'


@app.template_filter('format_date')
def format_date(d):
    if d:
        return d.strftime('%Y-%m-%d')
    return '-'


# ============== Main ==============

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        initialize_default_data()
        migrate_add_education_level()
    
    print("\n" + "="*60)
    print("PCG Hobor Church Financial Reporting App")
    print("="*60)
    print("\nStarting server...")
    print("Access the app at: http://localhost:5000")
    print("\nDefault Admin Credentials:")
    print("  Username: admin")
    print("  Password: admin123")
    print("\nIMPORTANT: Change the admin password after first login!")
    print("="*60 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
