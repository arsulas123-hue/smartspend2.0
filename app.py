from flask import Flask, render_template, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///smartspend.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


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
    transactions   = db.relationship('Transaction', backref='owner', lazy=True, foreign_keys='Transaction.user_id')
    budgets        = db.relationship('Budget', backref='owner', lazy=True, foreign_keys='Budget.user_id')

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

# --- DATABASE INITIALIZATION FUNCTION ---
TERMS_CONTENT = """<h3>SmartSpend Terms &amp; Conditions...</h3>""" # Keep your full HTML here


    with app.app_context():
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

# Call initialization once when the script loads
initialize_database()

# --- ROUTES (Keep your routes as they were) ---
# ... [Insert your @app.route functions here] ...

if __name__ == '__main__':
    app.run(debug=True)