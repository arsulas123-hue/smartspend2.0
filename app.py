from flask import Flask, render_template, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'smartspend_secret_key_2026')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///smartspend.db'
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
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
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
    tx_date    = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Budget(db.Model):
    __tablename__ = 'budget'
    budget_id  = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.user_id'), nullable=False)
    category   = db.Column(db.String(50), nullable=False)
    amount     = db.Column(db.Float, nullable=False)
    month      = db.Column(db.String(7), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AuditLog(db.Model):
    __tablename__ = 'audit_log'
    log_id     = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.user_id'), nullable=True)
    action     = db.Column(db.String(50), nullable=False)
    ip_address = db.Column(db.String(50), nullable=True)
    user_agent = db.Column(db.String(200), nullable=True)
    detail     = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class TermsVersion(db.Model):
    __tablename__ = 'terms_version'
    version_id  = db.Column(db.Integer, primary_key=True)
    version     = db.Column(db.String(10), unique=True, nullable=False)
    content     = db.Column(db.Text, nullable=False)
    is_active   = db.Column(db.Boolean, default=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

CURRENT_TERMS_VERSION = "1.0"

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
        return None, (jsonify({'error': 'Account inactive or not found'}), 403)
    if role == 'admin' and user.role != 'admin':
        return None, (jsonify({'error': 'Admin access required'}), 403)
    return user, None

@app.route('/api/terms')
def get_terms():
    t = TermsVersion.query.filter_by(version=CURRENT_TERMS_VERSION, is_active=True).first()
    if not t:
        return jsonify({'error': 'No active terms'}), 404
    return jsonify({'version': t.version, 'content': t.content})

@app.route('/api/register', methods=['POST'])
def register():
    data     = request.get_json() or {}
    name     = (data.get('name') or '').strip()
    email    = (data.get('email') or '').strip().lower()
    password = data.get('password', '')
    if not name or not email or not password:
        return jsonify({'error': 'All fields are required'}), 400
    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400
    if not data.get('accepted_terms'):
        return jsonify({'error': 'You must accept the Terms & Conditions to register'}), 400
    if data.get('terms_version') != CURRENT_TERMS_VERSION:
        return jsonify({'error': 'Please accept the latest Terms & Conditions'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'This email is already registered'}), 409
    user = User(name=name, email=email,
                password_hash=generate_password_hash(password),
                role='user', accepted_terms=True,
                terms_version=CURRENT_TERMS_VERSION,
                terms_date=datetime.utcnow(), is_active=True)
    db.session.add(user)
    db.session.commit()
    log_event('register', user_id=user.user_id, detail=f'email={email}')
    return jsonify({'message': 'Account created! You can now log in.'}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data     = request.get_json() or {}
    email    = (data.get('email') or '').strip().lower()
    password = data.get('password', '')
    user     = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        log_event('failed_login', detail=f'email={email}')
        return jsonify({'error': 'Invalid email or password'}), 401
    if not user.is_active:
        return jsonify({'error': 'This account has been disabled. Contact support.'}), 403
    user.last_login  = datetime.utcnow()
    user.login_count = (user.login_count or 0) + 1
    db.session.commit()
    session['user_id']   = user.user_id
    session['user_name'] = user.name
    session['role']      = user.role
    log_event('login', user_id=user.user_id)
    return jsonify({'message': 'Logged in',
                    'user': {'id': user.user_id, 'name': user.name,
                             'email': user.email, 'role': user.role}})

@app.route('/api/logout', methods=['POST', 'GET'])
def logout():
    log_event('logout', user_id=session.get('user_id'))
    session.clear()
    return jsonify({'message': 'Logged out'})

@app.route('/api/me')
def me():
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': 'Not logged in'}), 401
    user = User.query.get(uid)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify({'id': user.user_id, 'name': user.name, 'email': user.email,
                    'role': user.role,
                    'created_at': user.created_at.isoformat() if user.created_at else None,
                    'last_login': user.last_login.isoformat() if user.last_login else None,
                    'login_count': user.login_count or 0,
                    'accepted_terms': user.accepted_terms,
                    'terms_version': user.terms_version})

@app.route('/api/admin/users')
def admin_users():
    _, err = require_role('admin')
    if err: return err
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify([{'id': u.user_id, 'name': u.name, 'email': u.email,
                     'role': u.role, 'is_active': u.is_active,
                     'login_count': u.login_count or 0,
                     'last_login': u.last_login.isoformat() if u.last_login else None,
                     'created_at': u.created_at.isoformat() if u.created_at else None,
                     'accepted_terms': u.accepted_terms,
                     'terms_version': u.terms_version or '—',
                     'tx_count': len(u.transactions)} for u in users])

@app.route('/api/admin/users/<int:uid>/toggle', methods=['POST'])
def admin_toggle_user(uid):
    admin, err = require_role('admin')
    if err: return err
    if uid == admin.user_id:
        return jsonify({'error': 'Cannot disable your own account'}), 400
    user = User.query.get_or_404(uid)
    user.is_active = not user.is_active
    db.session.commit()
    log_event('admin_toggle', user_id=admin.user_id, detail=f'target={uid} active={user.is_active}')
    return jsonify({'is_active': user.is_active})

@app.route('/api/admin/users/<int:uid>/role', methods=['POST'])
def admin_change_role(uid):
    admin, err = require_role('admin')
    if err: return err
    data     = request.get_json() or {}
    new_role = data.get('role', 'user')
    if new_role not in ('user', 'admin'):
        return jsonify({'error': 'Invalid role'}), 400
    user      = User.query.get_or_404(uid)
    user.role = new_role
    db.session.commit()
    log_event('admin_role_change', user_id=admin.user_id, detail=f'target={uid} role={new_role}')
    return jsonify({'role': user.role})

@app.route('/api/admin/logs')
def admin_logs():
    _, err = require_role('admin')
    if err: return err
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(200).all()
    return jsonify([{'id': l.log_id, 'action': l.action, 'user_id': l.user_id,
                     'ip': l.ip_address, 'detail': l.detail,
                     'created_at': l.created_at.isoformat()} for l in logs])

@app.route('/api/admin/stats')
def admin_stats():
    _, err = require_role('admin')
    if err: return err
    return jsonify({'total_users': User.query.count(),
                    'active_users': User.query.filter_by(is_active=True).count(),
                    'admin_count': User.query.filter_by(role='admin').count(),
                    'total_transactions': Transaction.query.count(),
                    'total_logins': AuditLog.query.filter_by(action='login').count()})

@app.route('/api/transactions', methods=['GET'])
def get_transactions():
    user, err = require_role('user')
    if err: return err
    txs = Transaction.query.filter_by(user_id=user.user_id).order_by(Transaction.tx_date.desc()).all()
    return jsonify([{'tx_id': t.tx_id, 'amount': t.amount, 'category': t.category,
                     'tx_type': t.tx_type, 'note': t.note,
                     'tx_date': t.tx_date.isoformat() if t.tx_date else None} for t in txs])

@app.route('/api/transactions', methods=['POST'])
def add_transaction():
    user, err = require_role('user')
    if err: return err
    data = request.get_json() or {}
    tx = Transaction(user_id=user.user_id, amount=float(data['amount']),
                     category=data['category'], tx_type=data['tx_type'],
                     note=data.get('note', ''), tx_date=datetime.utcnow())
    db.session.add(tx)
    db.session.commit()
    return jsonify({'tx_id': tx.tx_id}), 201

@app.route('/api/transactions/<int:tx_id>', methods=['DELETE'])
def delete_transaction(tx_id):
    user, err = require_role('user')
    if err: return err
    tx = Transaction.query.filter_by(tx_id=tx_id, user_id=user.user_id).first_or_404()
    db.session.delete(tx)
    db.session.commit()
    return jsonify({'message': 'Deleted'})

@app.route('/api/summary/<int:uid>')
def summary(uid):
    user, err = require_role('user')
    if err: return err
    if user.user_id != uid and user.role != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    txs = Transaction.query.filter_by(user_id=uid).all()
    income  = sum(t.amount for t in txs if t.tx_type == 'income')
    expense = sum(t.amount for t in txs if t.tx_type == 'expense')
    return jsonify({'income': income, 'expense': expense, 'balance': income - expense})

@app.route('/api/predict/<int:uid>')
def predict(uid):
    user, err = require_role('user')
    if err: return err
    if user.user_id != uid and user.role != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    from collections import defaultdict
    txs  = Transaction.query.filter_by(user_id=uid, tx_type='expense').all()
    cats = defaultdict(float)
    for t in txs: cats[t.category] += t.amount
    total     = sum(cats.values()) or 1
    breakdown = [{'category': k, 'amount': round(v,2), 'pct': round(v/total*100,1)}
                 for k,v in sorted(cats.items(), key=lambda x: -x[1])]
    return jsonify({'breakdown': breakdown})

@app.route('/api/budgets/<int:uid>', methods=['GET'])
def get_budgets(uid):
    user, err = require_role('user')
    if err: return err
    if user.user_id != uid and user.role != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    budgets = Budget.query.filter_by(user_id=uid).all()
    return jsonify([{'budget_id': b.budget_id, 'category': b.category,
                     'amount': b.amount, 'month': b.month} for b in budgets])

@app.route('/api/budgets/<int:uid>', methods=['POST'])
def set_budget(uid):
    user, err = require_role('user')
    if err: return err
    if user.user_id != uid:
        return jsonify({'error': 'Forbidden'}), 403
    data     = request.get_json() or {}
    month    = data.get('month', datetime.utcnow().strftime('%Y-%m'))
    existing = Budget.query.filter_by(user_id=uid, category=data['category'], month=month).first()
    if existing:
        existing.amount = float(data['amount'])
    else:
        db.session.add(Budget(user_id=uid, category=data['category'],
                              amount=float(data['amount']), month=month))
    db.session.commit()
    return jsonify({'message': 'Budget saved'})

@app.route('/')
def index():
    return render_template('index.html')

TERMS_CONTENT = """<h3>SmartSpend Terms &amp; Conditions <span style="font-size:0.75rem;color:#5a7a94">v1.0 &middot; April 2026</span></h3>
<h4>1. Acceptance of Terms</h4><p>By creating an account and using SmartSpend (&ldquo;the Service&rdquo;), you agree to be bound by these Terms and Conditions. If you do not agree, you may not use the Service. These terms apply to all users, including regular users and administrators.</p>
<h4>2. User Accounts</h4><p>You are responsible for maintaining the confidentiality of your account credentials. You must immediately notify us of any unauthorized use. Each person may maintain only one account. You agree to provide accurate and complete registration information.</p>
<h4>3. Data Privacy &amp; Security</h4><p>Your financial data is stored locally in a SQLite database. We do not sell or transfer your personal information to third parties. All passwords are hashed using bcrypt. We implement reasonable security measures but cannot guarantee absolute security.</p>
<h4>4. Acceptable Use</h4><p>You agree not to: (a) use the Service for any unlawful purpose; (b) attempt unauthorized access; (c) interfere with or disrupt the Service; (d) create multiple accounts; (e) impersonate any person or entity.</p>
<h4>5. Financial Data Disclaimer</h4><p>SmartSpend is a personal finance tracking tool. It does not provide financial, investment, or legal advice. All predictions and analytics are for informational purposes only. You are solely responsible for your financial decisions.</p>
<h4>6. Admin Rights</h4><p>Administrators may view user account information for system maintenance. Admins may disable accounts that violate these terms. All admin actions are logged for accountability and transparency.</p>
<h4>7. Account Termination</h4><p>We reserve the right to suspend or terminate your account if you violate these Terms. You may request deletion of your account and data at any time by contacting support.</p>
<h4>8. Changes to Terms</h4><p>We may update these Terms from time to time. Continued use after changes constitutes acceptance. We will notify users of significant changes via in-app notification.</p>
<h4>9. Limitation of Liability</h4><p>SmartSpend is provided &ldquo;as is&rdquo; without warranties. We shall not be liable for any indirect, incidental, or consequential damages arising from your use of the Service.</p>
<h4>10. Governing Law</h4><p>These Terms are governed by the laws of the Philippines. This Service is developed as a WMSU Thesis Project (2026). For support: support@smartspend.ai</p>"""

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not TermsVersion.query.filter_by(version='1.0').first():
            db.session.add(TermsVersion(version='1.0', content=TERMS_CONTENT, is_active=True))
            db.session.commit()
        if not User.query.filter_by(role='admin').first():
            admin = User(name='Admin', email='admin@smartspend.ai',
                         password_hash=generate_password_hash('Admin@123'),
                         role='admin', accepted_terms=True,
                         terms_version='1.0', terms_date=datetime.utcnow(), is_active=True)
            db.session.add(admin)
            db.session.commit()
            print("Admin: admin@smartspend.ai / Admin@123")
    app.run(debug=True)
