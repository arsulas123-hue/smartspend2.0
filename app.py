from flask import Flask, render_template, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)

# 1. Configuration
app.secret_key = os.environ.get('SECRET_KEY', 'smartspend_secret_key_2026')
database_url = os.environ.get('DATABASE_URL')

# Fix the 'postgres://' vs 'postgresql://' issue for SQLAlchemy 1.4+
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

# FORCE PostgreSQL on Render, use SQLite ONLY for local testing
app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///smartspend.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- MODELS ---
class User(db.Model):
    __tablename__ = 'user'
    user_id        = db.Column(db.Integer, primary_key=True)
    name           = db.Column(db.String(100), nullable=False)
    email          = db.Column(db.String(120), unique=True, nullable=False)
    password_hash  = db.Column(db.String(255), nullable=False)
    role           = db.Column(db.String(20), default='user')
    is_active      = db.Column(db.Boolean, default=True)
    accepted_terms = db.Column(db.Boolean, default=False)
    terms_version  = db.Column(db.String(10), nullable=True)
    terms_date     = db.Column(db.DateTime, nullable=True)
    created_at     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_login     = db.Column(db.DateTime, nullable=True)
    login_count    = db.Column(db.Integer, default=0)
    transactions   = db.relationship('Transaction', backref='owner', lazy=True)

class Transaction(db.Model):
    __tablename__ = 'transaction'
    tx_id      = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.user_id'), nullable=False)
    amount     = db.Column(db.Float, nullable=False)
    category   = db.Column(db.String(50), nullable=False)
    tx_type    = db.Column(db.String(10), nullable=False) # 'income' or 'expense'
    note       = db.Column(db.String(200))
    tx_date    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class Budget(db.Model):
    __tablename__ = 'budget'
    budget_id  = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.user_id'), nullable=False)
    category   = db.Column(db.String(50), nullable=False)
    amount     = db.Column(db.Float, nullable=False)
    month      = db.Column(db.String(7), nullable=False) # YYYY-MM
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class AuditLog(db.Model):
    __tablename__ = 'audit_log'
    log_id     = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, nullable=True)
    action     = db.Column(db.String(50), nullable=False)
    ip_address = db.Column(db.String(50), nullable=True)
    user_agent = db.Column(db.String(200), nullable=True)
    detail     = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class TermsVersion(db.Model):
    __tablename__ = 'terms_version'
    version_id  = db.Column(db.Integer, primary_key=True)
    version     = db.Column(db.String(10), unique=True, nullable=False)
    content     = db.Column(db.Text, nullable=False)
    is_active   = db.Column(db.Boolean, default=True)
    created_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

# --- CONSTANTS & HELPERS ---
CURRENT_TERMS_VERSION = "1.0"
TERMS_CONTENT = """<h3>SmartSpend Terms & Conditions</h3><p>WMSU Thesis Project (2026). Governing Law: Philippines.</p>"""

def log_event(action, user_id=None, detail=None):
    try:
        entry = AuditLog(user_id=user_id, action=action,
                         ip_address=request.remote_addr,
                         user_agent=request.headers.get('User-Agent','')[:200],
                         detail=detail)
        db.session.add(entry)
        db.session.commit()
    except:
        pass

def require_role(role='user'):
    uid = session.get('user_id')
    if not uid:
        return None, (jsonify({'error': 'Not authenticated'}), 401)
    user = User.query.get(uid)
    if not user or not user.is_active:
        return None, (jsonify({'error': 'Account inactive'}), 403)
    if role == 'admin' and user.role != 'admin':
        return None, (jsonify({'error': 'Admin access required'}), 403)
    return user, None

# --- ROUTES ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already exists'}), 409
    
    user = User(name=data.get('name'), email=email,
                password_hash=generate_password_hash(data.get('password')),
                role='user', accepted_terms=True,
                terms_version=CURRENT_TERMS_VERSION,
                terms_date=datetime.now(timezone.utc), is_active=True)
    db.session.add(user)
    db.session.commit()
    return jsonify({'message': 'Account created!'}), 201

# --- DATABASE INITIALIZATION ---
def initialize_database():
    with app.app_context():
        db.create_all()
        # Seed Terms
        if not TermsVersion.query.filter_by(version=CURRENT_TERMS_VERSION).first():
            db.session.add(TermsVersion(version=CURRENT_TERMS_VERSION, content=TERMS_CONTENT, is_active=True))
        
        # Seed Admin
        if not User.query.filter_by(role='admin').first():
            admin = User(name='Admin', email='admin@smartspend.ai',
                         password_hash=generate_password_hash('Admin@123'),
                         role='admin', accepted_terms=True,
                         terms_version=CURRENT_TERMS_VERSION, 
                         terms_date=datetime.now(timezone.utc), is_active=True)
            db.session.add(admin)
        db.session.commit()

initialize_database()

if __name__ == '__main__':
    app.run(debug=True)