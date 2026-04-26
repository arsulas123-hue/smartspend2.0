from flask import Flask, render_template, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)

# --- 1. CONFIGURATION ---
app.secret_key = os.environ.get('SECRET_KEY', 'smartspend_secret_key_2026')
database_url = os.environ.get('DATABASE_URL')

# Fail immediately if DATABASE_URL is missing
if not database_url:
    raise RuntimeError("CRITICAL ERROR: DATABASE_URL is not set in Render Environment Variables!")

# Fix the 'postgres://' vs 'postgresql://' issue
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


# --- 2. MODELS ---
class User(db.Model):
    __tablename__ = 'user'
    user_id        = db.Column(db.Integer, primary_key=True)
    name           = db.Column(db.String(100), nullable=False)
    email          = db.Column(db.String(120), unique=True, nullable=False)
    password_hash  = db.Column(db.Text, nullable=False)
    role           = db.Column(db.String(20), default='user')
    is_active      = db.Column(db.Boolean, default=True)
    accepted_terms = db.Column(db.Boolean, default=False)
    terms_version  = db.Column(db.String(10), nullable=True)
    terms_date     = db.Column(db.DateTime, nullable=True)
    created_at     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_login     = db.Column(db.DateTime, nullable=True)
    login_count    = db.Column(db.Integer, default=0)

class Transaction(db.Model):
    __tablename__ = 'transaction'
    tx_id      = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.user_id'), nullable=False)
    amount     = db.Column(db.Float, nullable=False)
    category   = db.Column(db.String(50), nullable=False)
    tx_type    = db.Column(db.String(10), nullable=False)
    note       = db.Column(db.String(200))
    tx_date    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class Budget(db.Model):
    __tablename__ = 'budget'
    budget_id  = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.user_id'), nullable=False)
    category   = db.Column(db.String(50), nullable=False)
    amount     = db.Column(db.Float, nullable=False)
    month      = db.Column(db.String(7), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class AuditLog(db.Model):
    __tablename__ = 'audit_log'
    log_id     = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.user_id'), nullable=True)
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

   # --- 3. THE BRUTE FORCE SYNC & INITIALIZATION ---
TERMS_CONTENT = "<h3>SmartSpend Terms & Conditions</h3><p>WMSU Thesis Project (2026).</p>"

def force_database_sync():
    """Acts like a manual shell command to ensure tables exist in PostgreSQL"""
    with app.app_context():
        # Create tables
        db.create_all()
        
        # Seed Terms
        if not TermsVersion.query.filter_by(version='1.0').first():
            db.session.add(TermsVersion(version='1.0', content=TERMS_CONTENT, is_active=True))
        
        # Seed Admin
        if not User.query.filter_by(role='admin').first():
            admin = User(
                name='Admin', 
                email='admin@smartspend.ai',
                password_hash=generate_password_hash('Admin@123'),
                role='admin', 
                accepted_terms=True,
                terms_version='1.0', 
                terms_date=datetime.now(timezone.utc), 
                is_active=True
            )
            db.session.add(admin)
        
        db.session.commit()
        print("Database Brute Force Sync: Complete")

# Execute the sync immediately when the app script is loaded by Gunicorn
force_database_sync()


# [Note: Insert your /api/register and other routes here]
# --- 4. ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    # Validation
    if User.query.filter_by(email=data.get('email')).first():
        return jsonify({'error': 'Email already exists'}), 400
    
    # Create User
    new_user = User(
        name=data.get('name'),
        email=data.get('email'),
        password_hash=generate_password_hash(data.get('password')),
        accepted_terms=True,
        terms_version='1.0',
        terms_date=datetime.now(timezone.utc)
    )
    db.session.add(new_user)
    db.session.commit()
    return jsonify({'message': 'Registration successful!'}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user = User.query.filter_by(email=data.get('email')).first()
    
    if user and check_password_hash(user.password_hash, data.get('password')):
        session['user_id'] = user.user_id
        user.last_login = datetime.now(timezone.utc)
        user.login_count += 1
        db.session.commit()
        return jsonify({'message': 'Login successful', 'user': {'name': user.name, 'role': user.role}})
    
    return jsonify({'error': 'Invalid email or password'}), 401

@app.route('/api/terms', methods=['GET'])
def get_terms():
    terms = TermsVersion.query.filter_by(is_active=True).first()
    return jsonify({'content': terms.content if terms else "Terms not found"})

@app.route('/api/me', methods=['GET'])
def get_me():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not logged in'}), 401
    user = User.query.get(user_id)
    return jsonify({'name': user.name, 'email': user.email, 'role': user.role})  
 

if __name__ == '__main__':
    app.run(debug=True)
    

