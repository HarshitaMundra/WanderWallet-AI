import os
import sys
from pathlib import Path
from dotenv import load_dotenv

env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path, override=True)

if not os.getenv('GEMINI_API_KEY'):
    print("WARNING: GEMINI_API_KEY not found in environment!")
    print(f"Looking for .env file at: {env_path.absolute()}")
    print(f".env file exists: {env_path.exists()}")

import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import json
import requests
from utils.ai_engine import predict_trip_budget, generate_budget_advice, create_travel_plan, get_city_accommodations, get_city_tourist_spots, get_ai_travel_options, select_best_destination_images, generate_personalized_budget_insights

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SESSION_SECRET', 'dev-secret-key-change-in-production')
UNSPLASH_ACCESS_KEY = os.environ.get('UNSPLASH_ACCESS_KEY', '')

if UNSPLASH_ACCESS_KEY:
    app.logger.info(f"Unsplash API key loaded: {UNSPLASH_ACCESS_KEY[:8]}...")
else:
    app.logger.warning("Unsplash API key not found - will use fallback images")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # type: ignore

DATABASE = 'database.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with app.app_context():
        db = get_db()
        db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                income REAL NOT NULL,
                needs REAL NOT NULL,
                wants REAL NOT NULL,
                savings REAL NOT NULL,
                month TEXT NOT NULL,
                year INTEGER NOT NULL,
                ai_insights TEXT,
                needs_subcategories TEXT,
                wants_subcategories TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS travel_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                start_city TEXT NOT NULL,
                destination TEXT NOT NULL,
                travel_days INTEGER NOT NULL,
                travel_month TEXT NOT NULL,
                total_budget REAL,
                monthly_savings REAL,
                status TEXT DEFAULT 'planning',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS savings_goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                month TEXT NOT NULL,
                year INTEGER NOT NULL,
                goal_amount REAL NOT NULL,
                achieved_amount REAL DEFAULT 0,
                milestones TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id, month, year)
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS image_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                image_index INTEGER DEFAULT 0,
                image_url TEXT NOT NULL,
                photographer TEXT,
                photographer_url TEXT,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(query, image_index)
            )
        ''')
        
        try:
            db.execute('SELECT image_index FROM image_cache LIMIT 1')
        except sqlite3.OperationalError:
            app.logger.info('Migrating image_cache table to add image_index column')
            db.execute('DROP TABLE IF EXISTS image_cache')
            db.execute('''
                CREATE TABLE image_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    image_index INTEGER DEFAULT 0,
                    image_url TEXT NOT NULL,
                    photographer TEXT,
                    photographer_url TEXT,
                    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(query, image_index)
                )
            ''')
        
        try:
            db.execute('SELECT needs_subcategories FROM budgets LIMIT 1')
        except sqlite3.OperationalError:
            app.logger.info('Adding subcategories columns to budgets table')
            db.execute('ALTER TABLE budgets ADD COLUMN needs_subcategories TEXT')
            db.execute('ALTER TABLE budgets ADD COLUMN wants_subcategories TEXT')
        
        db.commit()
        db.close()

class User(UserMixin):
    def __init__(self, id, username, email):
        self.id = id
        self.username = username
        self.email = email

@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    db.close()
    if user:
        return User(user['id'], user['username'], user['email'])
    return None

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('landing.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password', '')
        
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        db.close()
        
        if user and password and check_password_hash(user['password'], password):
            user_obj = User(user['id'], user['username'], user['email'])
            login_user(user_obj)
            flash(f'Welcome back, {user["username"]}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password', 'error')
    
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password', '')
        
        db = get_db()
        existing_user = db.execute('SELECT * FROM users WHERE email = ? OR username = ?', 
                                   (email, username)).fetchone()
        
        if existing_user:
            flash('Email or username already exists', 'error')
        elif password:
            hashed_password = generate_password_hash(password)
            db.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
                      (username, email, hashed_password))
            db.commit()
            db.close()
            flash('Account created successfully! Please login.', 'success')
            return redirect(url_for('login'))
        
        db.close()
    
    return render_template('signup.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out successfully', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    
    current_budget = db.execute('SELECT * FROM budgets WHERE user_id = ? ORDER BY created_at DESC LIMIT 1', 
                               (current_user.id,)).fetchone()
    
    all_budgets = db.execute('SELECT * FROM budgets WHERE user_id = ? ORDER BY created_at DESC LIMIT 6', 
                            (current_user.id,)).fetchall()
    
    previous_budget = db.execute('SELECT * FROM budgets WHERE user_id = ? ORDER BY created_at DESC LIMIT 1 OFFSET 1', 
                                (current_user.id,)).fetchone()
    
    next_trip = db.execute('SELECT * FROM travel_plans WHERE user_id = ? ORDER BY created_at DESC LIMIT 1', 
                          (current_user.id,)).fetchone()
    
    monthly_income = current_budget['income'] if current_budget else 0
    monthly_needs = current_budget['needs'] if current_budget else 0
    monthly_wants = current_budget['wants'] if current_budget else 0
    monthly_savings = current_budget['savings'] if current_budget else 0
    monthly_expenses = monthly_needs + monthly_wants
    
    savings_rate = (monthly_savings / monthly_income * 100) if monthly_income > 0 else 0
    
    income_change = 0
    if previous_budget and previous_budget['income'] > 0:
        income_change = ((monthly_income - previous_budget['income']) / previous_budget['income'] * 100)
    
    months = []
    income_data = []
    expenses_data = []
    savings_data = []
    
    for budget in reversed(all_budgets):
        months.append(f"{budget['month'][:3]} {str(budget['year'])[2:]}")
        income_data.append(float(budget['income']))
        expenses_data.append(float(budget['needs'] + budget['wants']))
        savings_data.append(float(budget['savings']))
    
    monthly_data = {
        'months': months,
        'income': income_data,
        'expenses': expenses_data,
        'savings': savings_data
    }
    
    destination_images = []
    if next_trip and next_trip['destination']:
        images = fetch_unsplash_images(f"{next_trip['destination']} India", 4)
        if images and len(images) > 0:
            destination_images = [img['url'] for img in images]
            app.logger.info(f"Fetched {len(destination_images)} images for {next_trip['destination']}")
    
    if not destination_images:
        destination_images = [
            'https://images.unsplash.com/photo-1524492412937-b28074a5d7da?w=400',
            'https://images.unsplash.com/photo-1469854523086-cc02fe5d8800?w=400',
            'https://images.unsplash.com/photo-1476514525535-07fb3b4ae5f1?w=400',
            'https://images.unsplash.com/photo-1530789253388-582c481c54b0?w=400'
        ]
        app.logger.warning(f"Using fallback images for destination preview")
    
    savings_goal = db.execute('''SELECT * FROM savings_goals 
                                 WHERE user_id = ? AND month = ? AND year = ? 
                                 LIMIT 1''',
                             (current_user.id, datetime.now().strftime('%B'), 
                              datetime.now().year)).fetchone()
    
    milestones = []
    if savings_goal and savings_goal['milestones']:
        try:
            milestones = json.loads(savings_goal['milestones'])
        except:
            milestones = []
    
    recent_notes = db.execute('''SELECT * FROM notes WHERE user_id = ? 
                                 ORDER BY updated_at DESC LIMIT 3''',
                             (current_user.id,)).fetchall()
    
    db.close()
    
    return render_template('dashboard.html',
                         monthly_income=monthly_income,
                         monthly_expenses=monthly_expenses,
                         monthly_savings=monthly_savings,
                         monthly_needs=monthly_needs,
                         monthly_wants=monthly_wants,
                         savings_rate=savings_rate,
                         income_change=income_change,
                         next_trip=next_trip,
                         recent_budgets=all_budgets[:5],
                         monthly_data=monthly_data,
                         destination_images=destination_images,
                         savings_milestones=milestones,
                         recent_notes=recent_notes)

@app.route('/api/budgets', methods=['GET'])
@login_required
def get_budget():
    month = request.args.get('month')
    year = request.args.get('year')
    
    if not month or not year:
        return jsonify({'success': False, 'error': 'Month and year are required'}), 400
    
    try:
        year = int(year)
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid year'}), 400
    
    db = get_db()
    budget = db.execute(
        'SELECT * FROM budgets WHERE user_id = ? AND month = ? AND year = ? ORDER BY created_at DESC LIMIT 1',
        (current_user.id, month, year)
    ).fetchone()
    db.close()
    
    if budget:
        ai_insights = None
        if budget['ai_insights']:
            try:
                ai_insights = json.loads(budget['ai_insights'])
            except:
                pass
        
        needs_subcategories = {}
        wants_subcategories = {}
        if budget['needs_subcategories']:
            try:
                needs_subcategories = json.loads(budget['needs_subcategories'])
            except:
                pass
        if budget['wants_subcategories']:
            try:
                wants_subcategories = json.loads(budget['wants_subcategories'])
            except:
                pass
        
        return jsonify({
            'success': True,
            'data': {
                'income': budget['income'],
                'needs': budget['needs'],
                'wants': budget['wants'],
                'savings': budget['savings'],
                'needs_subcategories': needs_subcategories,
                'wants_subcategories': wants_subcategories
            },
            'insights': ai_insights
        })
    else:
        return jsonify({'success': False, 'message': 'No budget found for this month'})

@app.route('/budget', methods=['GET', 'POST'])
@login_required
def budget():
    if request.method == 'POST':
        income = float(request.form.get('income', 0))
        needs = float(request.form.get('needs', 0))
        wants = float(request.form.get('wants', 0))
        savings = float(request.form.get('savings', 0))
        
        month = request.form.get('month', datetime.now().strftime('%B'))
        year = int(request.form.get('year', datetime.now().year))
        
        needs_subcategories = request.form.get('needs_subcategories', '{}')
        wants_subcategories = request.form.get('wants_subcategories', '{}')
        
        app.logger.info(f'Received budget POST - needs_subcategories: {needs_subcategories}, wants_subcategories: {wants_subcategories}')
        
        try:
            json.loads(needs_subcategories)
            json.loads(wants_subcategories)
        except json.JSONDecodeError as e:
            app.logger.error(f'Invalid JSON in subcategories: {e}')
            needs_subcategories = '{}'
            wants_subcategories = '{}'
        
        ai_insights = generate_budget_insights(income, needs, wants, savings)
        
        db = get_db()
        
        existing_budget = db.execute(
            'SELECT id FROM budgets WHERE user_id = ? AND month = ? AND year = ?',
            (current_user.id, month, year)
        ).fetchone()
        
        if existing_budget:
            db.execute('''UPDATE budgets 
                         SET income = ?, needs = ?, wants = ?, savings = ?, ai_insights = ?, 
                             needs_subcategories = ?, wants_subcategories = ?
                         WHERE id = ?''',
                      (income, needs, wants, savings, json.dumps(ai_insights), 
                       needs_subcategories, wants_subcategories, existing_budget['id']))
        else:
            db.execute('''INSERT INTO budgets (user_id, income, needs, wants, savings, month, year, ai_insights, 
                                              needs_subcategories, wants_subcategories)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (current_user.id, income, needs, wants, savings, month, year, json.dumps(ai_insights),
                       needs_subcategories, wants_subcategories))
        
        db.commit()
        db.close()
        
        return jsonify({
            'success': True,
            'insights': ai_insights,
            'data': {
                'income': income,
                'needs': needs,
                'wants': wants,
                'savings': savings,
                'needs_subcategories': json.loads(needs_subcategories) if needs_subcategories else {},
                'wants_subcategories': json.loads(wants_subcategories) if wants_subcategories else {}
            }
        })
    
    db = get_db()
    
    all_budgets = db.execute('''
        SELECT * FROM budgets WHERE user_id = ? 
        ORDER BY year DESC, created_at DESC
    ''', (current_user.id,)).fetchall()
    
    recent_budgets = db.execute('''
        SELECT * FROM budgets WHERE user_id = ? 
        AND (month, year, created_at) IN (
            SELECT month, year, MAX(created_at) 
            FROM budgets 
            WHERE user_id = ? 
            GROUP BY month, year
        )
        ORDER BY year DESC, 
                 CASE month 
                    WHEN 'January' THEN 1 
                    WHEN 'February' THEN 2 
                    WHEN 'March' THEN 3 
                    WHEN 'April' THEN 4 
                    WHEN 'May' THEN 5 
                    WHEN 'June' THEN 6 
                    WHEN 'July' THEN 7 
                    WHEN 'August' THEN 8 
                    WHEN 'September' THEN 9 
                    WHEN 'October' THEN 10 
                    WHEN 'November' THEN 11 
                    WHEN 'December' THEN 12 
                 END DESC
        LIMIT 3
    ''', (current_user.id, current_user.id)).fetchall()
    
    db.close()
    
    return render_template('budget.html', budgets=all_budgets, recent_budgets=recent_budgets)

@app.route('/travel', methods=['GET', 'POST'])
@login_required
def travel():
    if request.method == 'POST':
        start_city = request.form.get('start_city')
        destination = request.form.get('destination')
        travel_days = int(request.form.get('travel_days', 1))
        travel_month = request.form.get('travel_month')
        
        travel_data = get_travel_options(start_city, destination, travel_days, travel_month)
        
        db = get_db()
        db.execute('''INSERT INTO travel_plans (user_id, start_city, destination, travel_days, 
                     travel_month, total_budget, monthly_savings)
                     VALUES (?, ?, ?, ?, ?, ?, ?)''',
                  (current_user.id, start_city, destination, travel_days, travel_month,
                   travel_data['total_budget'], travel_data['monthly_savings']))
        db.commit()
        plan_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        db.close()
        
        return jsonify({
            'success': True,
            'plan_id': plan_id,
            'data': travel_data
        })
    
    return render_template('travel.html')

@app.route('/accommodation/<int:plan_id>')
@login_required
def accommodation(plan_id):
    db = get_db()
    plan = db.execute('SELECT * FROM travel_plans WHERE id = ? AND user_id = ?', 
                     (plan_id, current_user.id)).fetchone()
    db.close()
    
    if not plan:
        flash('Travel plan not found', 'error')
        return redirect(url_for('travel'))
    
    accommodations = get_accommodations(plan['destination'])
    tourist_spots = get_tourist_spots(plan['destination'])
    
    destination_images = fetch_unsplash_images(f"{plan['destination']} city landmark", 1)
    tourist_images = []
    
    for i, spot in enumerate(tourist_spots):
        spot_name = spot.get('name', 'landmark')
        
        search_query = f"{spot_name} {plan['destination']}"
        images = fetch_unsplash_images(search_query, 1)
        
        if images:
            tourist_images.append(images[0])
        else:
            tourist_images.append({'url': 'https://images.unsplash.com/photo-1476514525535-07fb3b4ae5f1?w=400', 'photographer': '', 'photographer_url': ''})
    
    return render_template('accommodation.html', 
                         plan=plan,
                         accommodations=accommodations,
                         tourist_spots=tourist_spots,
                         destination_images=destination_images,
                         tourist_images=tourist_images)

@app.route('/plans')
@login_required
def plans():
    db = get_db()
    budgets = db.execute('SELECT * FROM budgets WHERE user_id = ? ORDER BY created_at DESC', 
                        (current_user.id,)).fetchall()
    travel_plans = db.execute('SELECT * FROM travel_plans WHERE user_id = ? ORDER BY created_at DESC', 
                             (current_user.id,)).fetchall()
    db.close()
    
    return render_template('plans.html', budgets=budgets, travel_plans=travel_plans)

@app.route('/profile')
@login_required
def profile():
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (current_user.id,)).fetchone()
    
    total_budgets = db.execute('SELECT COUNT(*) as count FROM budgets WHERE user_id = ?', 
                               (current_user.id,)).fetchone()['count']
    total_trips = db.execute('SELECT COUNT(*) as count FROM travel_plans WHERE user_id = ?', 
                            (current_user.id,)).fetchone()['count']
    total_saved = db.execute('SELECT SUM(savings) as total FROM budgets WHERE user_id = ?', 
                            (current_user.id,)).fetchone()['total'] or 0
    
    db.close()
    
    return render_template('profile.html', 
                         user=user,
                         total_budgets=total_budgets,
                         total_trips=total_trips,
                         total_saved=total_saved)

@app.route('/profile/update-email', methods=['POST'])
@login_required
def update_email():
    try:
        data = request.get_json()
        new_email = data.get('email')
        
        if not new_email:
            return jsonify({'success': False, 'message': 'Email is required'}), 400
        
        db = get_db()
        existing_user = db.execute('SELECT * FROM users WHERE email = ? AND id != ?', 
                                   (new_email, current_user.id)).fetchone()
        
        if existing_user:
            db.close()
            return jsonify({'success': False, 'message': 'Email already in use'}), 400
        
        db.execute('UPDATE users SET email = ? WHERE id = ?', (new_email, current_user.id))
        db.commit()
        db.close()
        
        current_user.email = new_email
        
        return jsonify({'success': True, 'message': 'Email updated successfully'}), 200
        
    except Exception as e:
        app.logger.error(f"Email update error: {e}")
        return jsonify({'success': False, 'message': 'An error occurred'}), 500

@app.route('/profile/change-password', methods=['POST'])
@login_required
def change_password():
    try:
        data = request.get_json()
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        
        if not current_password or not new_password:
            return jsonify({'success': False, 'message': 'All fields are required'}), 400
        
        if len(new_password) < 6:
            return jsonify({'success': False, 'message': 'Password must be at least 6 characters'}), 400
        
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE id = ?', (current_user.id,)).fetchone()
        
        if not check_password_hash(user['password'], current_password):
            db.close()
            return jsonify({'success': False, 'message': 'Current password is incorrect'}), 400
        
        hashed_password = generate_password_hash(new_password)
        db.execute('UPDATE users SET password = ? WHERE id = ?', (hashed_password, current_user.id))
        db.commit()
        db.close()
        
        return jsonify({'success': True, 'message': 'Password changed successfully'}), 200
        
    except Exception as e:
        app.logger.error(f"Password change error: {e}")
        return jsonify({'success': False, 'message': 'An error occurred'}), 500

@app.route('/notes', methods=['GET', 'POST'])
@login_required
def notes():
    db = get_db()
    
    if request.method == 'POST':
        try:
            data = request.get_json()
            title = data.get('title', '').strip()
            content = data.get('content', '').strip()
            
            if not title or not content:
                return jsonify({'success': False, 'message': 'Title and content are required'}), 400
            
            db.execute('''INSERT INTO notes (user_id, title, content)
                         VALUES (?, ?, ?)''',
                      (current_user.id, title, content))
            db.commit()
            note_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
            
            new_note = db.execute('SELECT * FROM notes WHERE id = ?', (note_id,)).fetchone()
            db.close()
            
            return jsonify({
                'success': True,
                'message': 'Note created successfully',
                'note': {
                    'id': new_note['id'],
                    'title': new_note['title'],
                    'content': new_note['content'],
                    'created_at': new_note['created_at'],
                    'updated_at': new_note['updated_at']
                }
            }), 200
            
        except Exception as e:
            app.logger.error(f"Note creation error: {e}")
            db.close()
            return jsonify({'success': False, 'message': 'An error occurred'}), 500
    
    all_notes = db.execute('''
        SELECT * FROM notes WHERE user_id = ? 
        ORDER BY updated_at DESC
    ''', (current_user.id,)).fetchall()
    
    db.close()
    
    notes_list = [dict(note) for note in all_notes]
    
    return render_template('notes.html', notes=notes_list)

@app.route('/api/notes/<int:note_id>', methods=['PUT', 'DELETE'])
@login_required
def manage_note(note_id):
    db = get_db()
    
    note = db.execute('SELECT * FROM notes WHERE id = ? AND user_id = ?', 
                     (note_id, current_user.id)).fetchone()
    
    if not note:
        db.close()
        return jsonify({'success': False, 'message': 'Note not found'}), 404
    
    if request.method == 'DELETE':
        try:
            db.execute('DELETE FROM notes WHERE id = ? AND user_id = ?', 
                      (note_id, current_user.id))
            db.commit()
            db.close()
            return jsonify({'success': True, 'message': 'Note deleted successfully'}), 200
        except Exception as e:
            app.logger.error(f"Note deletion error: {e}")
            db.close()
            return jsonify({'success': False, 'message': 'An error occurred'}), 500
    
    if request.method == 'PUT':
        try:
            data = request.get_json()
            title = data.get('title', '').strip()
            content = data.get('content', '').strip()
            
            if not title or not content:
                db.close()
                return jsonify({'success': False, 'message': 'Title and content are required'}), 400
            
            db.execute('''UPDATE notes 
                         SET title = ?, content = ?, updated_at = CURRENT_TIMESTAMP
                         WHERE id = ? AND user_id = ?''',
                      (title, content, note_id, current_user.id))
            db.commit()
            
            updated_note = db.execute('SELECT * FROM notes WHERE id = ?', (note_id,)).fetchone()
            db.close()
            
            return jsonify({
                'success': True,
                'message': 'Note updated successfully',
                'note': {
                    'id': updated_note['id'],
                    'title': updated_note['title'],
                    'content': updated_note['content'],
                    'created_at': updated_note['created_at'],
                    'updated_at': updated_note['updated_at']
                }
            }), 200
            
        except Exception as e:
            app.logger.error(f"Note update error: {e}")
            db.close()
            return jsonify({'success': False, 'message': 'An error occurred'}), 500

@app.route('/api/predict-trip-budget', methods=['POST'])
@login_required
def api_predict_trip_budget():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        required_fields = ['from', 'to', 'days', 'people', 'budget_goal']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        if data.get('days', 0) <= 0:
            return jsonify({'error': 'Days must be a positive number'}), 400
        if data.get('people', 0) <= 0:
            return jsonify({'error': 'People must be a positive number'}), 400
        if data.get('budget_goal', 0) < 0:
            return jsonify({'error': 'Budget goal cannot be negative'}), 400
        
        result = predict_trip_budget(data)
        
        return jsonify({
            'success': True,
            'data': result
        }), 200
        
    except Exception as e:
        app.logger.error(f"Trip budget prediction error: {e}")
        return jsonify({
            'success': False,
            'error': 'Unable to generate trip budget prediction. Please try again.'
        }), 500

@app.route('/api/budget-advice', methods=['POST'])
@login_required
def api_budget_advice():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        required_fields = ['income', 'expenses', 'savings_goal']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        if data.get('income', 0) < 0:
            return jsonify({'error': 'Income cannot be negative'}), 400
        if data.get('expenses', 0) < 0:
            return jsonify({'error': 'Expenses cannot be negative'}), 400
        if data.get('savings_goal', 0) < 0:
            return jsonify({'error': 'Savings goal cannot be negative'}), 400
        
        advice = generate_budget_advice(data)
        
        return jsonify({
            'success': True,
            'advice': advice
        }), 200
        
    except Exception as e:
        app.logger.error(f"Budget advice error: {e}")
        return jsonify({
            'success': False,
            'error': 'Unable to generate budget advice. Please try again.'
        }), 500

@app.route('/api/travel-plan', methods=['POST'])
@login_required
def api_travel_plan():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        required_fields = ['from', 'to', 'days']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        if data.get('days', 0) <= 0:
            return jsonify({'error': 'Days must be a positive number'}), 400
        
        result = create_travel_plan(data)
        
        return jsonify({
            'success': True,
            'data': result
        }), 200
        
    except Exception as e:
        app.logger.error(f"Travel plan error: {e}")
        return jsonify({
            'success': False,
            'error': 'Unable to generate travel plan. Please try again.'
        }), 500

@app.route('/api/travel-options', methods=['POST'])
@login_required
def api_travel_options():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        required_fields = ['from', 'to', 'days', 'month']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        start_city = data.get('from')
        destination = data.get('to')
        days = data.get('days')
        month = data.get('month')
        
        if days <= 0:
            return jsonify({'error': 'Days must be a positive number'}), 400
        
        result = get_ai_travel_options(start_city, destination, days, month)
        
        return jsonify({
            'success': True,
            'data': result
        }), 200
        
    except Exception as e:
        app.logger.error(f"Travel options error: {e}")
        return jsonify({
            'success': False,
            'error': 'Unable to fetch travel options. Please try again.'
        }), 500

@app.route('/api/savings-milestones', methods=['GET', 'POST'])
@login_required
def api_savings_milestones():
    db = get_db()
    current_month = datetime.now().strftime('%B')
    current_year = datetime.now().year
    
    if request.method == 'POST':
        try:
            data = request.get_json()
            milestones = data.get('milestones', [])
            goal_amount = data.get('goal_amount', 0)
            achieved_amount = data.get('achieved_amount', 0)
            
            existing = db.execute('''SELECT * FROM savings_goals 
                                     WHERE user_id = ? AND month = ? AND year = ?''',
                                 (current_user.id, current_month, current_year)).fetchone()
            
            if existing:
                db.execute('''UPDATE savings_goals 
                             SET milestones = ?, goal_amount = ?, achieved_amount = ? 
                             WHERE user_id = ? AND month = ? AND year = ?''',
                          (json.dumps(milestones), goal_amount, achieved_amount,
                           current_user.id, current_month, current_year))
            else:
                db.execute('''INSERT INTO savings_goals 
                             (user_id, month, year, goal_amount, achieved_amount, milestones) 
                             VALUES (?, ?, ?, ?, ?, ?)''',
                          (current_user.id, current_month, current_year, 
                           goal_amount, achieved_amount, json.dumps(milestones)))
            
            db.commit()
            db.close()
            
            return jsonify({'success': True}), 200
            
        except Exception as e:
            app.logger.error(f"Savings milestones error: {e}")
            db.close()
            return jsonify({'success': False, 'error': str(e)}), 500
    
    else:
        goal = db.execute('''SELECT * FROM savings_goals 
                            WHERE user_id = ? AND month = ? AND year = ?''',
                         (current_user.id, current_month, current_year)).fetchone()
        db.close()
        
        if goal:
            milestones = json.loads(goal['milestones']) if goal['milestones'] else []
            return jsonify({
                'success': True,
                'data': {
                    'milestones': milestones,
                    'goal_amount': goal['goal_amount'],
                    'achieved_amount': goal['achieved_amount']
                }
            }), 200
        else:
            return jsonify({
                'success': True,
                'data': {
                    'milestones': [],
                    'goal_amount': 0,
                    'achieved_amount': 0
                }
            }), 200

def generate_budget_insights(income, needs, wants, savings):
    total_expenses = needs + wants
    savings_rate = (savings / income * 100) if income > 0 else 0
    
    fallback_tips = []
    
    if wants > (income * 0.3):
        potential_savings = wants - (income * 0.3)
        fallback_tips.append(f'Consider reducing wants by ₹{potential_savings:.0f} to boost savings by {(potential_savings/income*100):.1f}%')
    
    if savings_rate < 20:
        fallback_tips.append('Try to save at least 20% of your income for a healthy financial future')
    elif savings_rate >= 30:
        fallback_tips.append('Excellent savings rate! You\'re on track for strong financial health')
    
    if needs > (income * 0.5):
        fallback_tips.append('Your needs are high. Look for ways to reduce fixed expenses')
    
    ai_insights = generate_personalized_budget_insights(income, needs, wants, savings)
    
    if ai_insights:
        combined_tips = list(ai_insights.get('tips', []))
        
        for tip in fallback_tips:
            if tip not in combined_tips:
                combined_tips.append(tip)
        
        return {
            'summary': ai_insights.get('summary', f'Your savings rate is {savings_rate:.1f}%.'),
            'tips': combined_tips
        }
    
    return {
        'summary': f'Your savings rate is {savings_rate:.1f}%. ',
        'tips': fallback_tips
    }

def get_travel_options(start_city, destination, days, month):
    return get_ai_travel_options(start_city, destination, days, month)

def get_accommodations(destination):
    return get_city_accommodations(destination)

def get_tourist_spots(destination):
    return get_city_tourist_spots(destination)

def fetch_unsplash_images(query, count=1):
    from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
    
    db = get_db()
    
    cached = db.execute(
        'SELECT * FROM image_cache WHERE query = ? ORDER BY image_index LIMIT ?', 
        (query, count)
    ).fetchall()
    
    if len(cached) >= count:
        db.close()
        return [{
            'url': img['image_url'],
            'photographer': img['photographer'],
            'photographer_url': img['photographer_url']
        } for img in cached[:count]]
    
    if not UNSPLASH_ACCESS_KEY:
        db.close()
        return get_fallback_images(query, count)
    
    people_keywords = {'selfie', 'portrait'}
    
    sanitized_query = ' '.join([word for word in query.lower().split() 
                                 if word not in people_keywords and not word.startswith('-')])
    
    destination_name = sanitized_query.split()[0] if sanitized_query else query
    
    words = sanitized_query.split()
    has_india = 'india' in words or 'indian' in words
    
    query_variations = [
        sanitized_query,
        f"{destination_name} landmark" if len(words) > 1 else sanitized_query,
        f"{destination_name} cityscape" if len(words) > 1 else f"{sanitized_query} city",
        f"india rajasthan heritage" if has_india else f"{destination_name} architecture",
        "india tourist attraction beautiful" if has_india else f"{sanitized_query} travel destination"
    ]
    
    max_attempts = len(query_variations)
    
    raw_photo_data = []
    filtered_photo_data = []
    
    for attempt in range(max_attempts):
        try:
            current_query = query_variations[attempt] if attempt < len(query_variations) else query_variations[0]
            
            url = "https://api.unsplash.com/search/photos"
            params = {
                'query': current_query,
                'per_page': 20,
                'orientation': 'landscape',
                'order_by': 'relevant',
                'content_filter': 'high'
            }
            headers = {
                'Authorization': f'Client-ID {UNSPLASH_ACCESS_KEY}'
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            app.logger.info(f"Unsplash API response status: {response.status_code}, Query: '{current_query}'")
            
            if response.status_code == 200:
                data = response.json()
                total_results = data.get('total', 0)
                results_count = len(data.get('results', []))
                app.logger.info(f"Unsplash returned {results_count} results out of {total_results} total")
                
                for photo in data.get('results', []):
                    raw_photo_data.append(photo)
                    
                    has_people_focus = False
                    tags = [tag.get('title', '').lower() for tag in photo.get('tags', [])]
                    alt_description = (photo.get('alt_description') or '').lower()
                    description = (photo.get('description') or '').lower()
                    
                    text_to_check = ' '.join(tags) + ' ' + alt_description + ' ' + description
                    
                    for keyword in people_keywords:
                        if keyword in text_to_check:
                            has_people_focus = True
                            break
                    
                    if not has_people_focus:
                        filtered_photo_data.append(photo)
                
                app.logger.info(f"Attempt {attempt + 1}/{max_attempts}: Query '{current_query}' returned {results_count} images. Total collected: {len(filtered_photo_data)} filtered, {len(raw_photo_data)} total")
                
                if len(filtered_photo_data) >= count * 2:
                    app.logger.info(f"Sufficient images collected, stopping search")
                    break
                
            else:
                app.logger.error(f"Unsplash API error on attempt {attempt + 1}: {response.status_code}")
                
        except Exception as e:
            app.logger.error(f"Error fetching Unsplash images on attempt {attempt + 1}: {e}")
    
    if filtered_photo_data:
        raw_photo_data = filtered_photo_data
    
    if not raw_photo_data:
        db.close()
        return get_fallback_images(query, count)
    
    ranked_indices = select_best_destination_images(destination_name, raw_photo_data)
    
    accumulated_images = []
    used_photo_ids = set()
    used_urls = set()
    
    for idx in ranked_indices:
        if len(accumulated_images) >= count:
            break
            
        if idx < len(raw_photo_data):
            photo = raw_photo_data[idx]
            photo_id = photo.get('id', '')
            
            if photo_id in used_photo_ids:
                continue
            
            base_url = photo['urls']['regular']
            parsed = urlparse(base_url)
            existing_params = parse_qsl(parsed.query, keep_blank_values=True)
            
            param_dict = {key: value for key, value in existing_params}
            
            if 'auto' not in param_dict:
                param_dict['auto'] = 'format'
            if 'q' not in param_dict:
                param_dict['q'] = '80'
            if 'w' not in param_dict:
                param_dict['w'] = '1200'
            
            new_params = [(k, v) for k, v in param_dict.items()]
            
            new_query = urlencode(new_params)
            optimized_url = urlunparse((
                parsed.scheme, parsed.netloc, parsed.path,
                parsed.params, new_query, parsed.fragment
            ))
            
            if optimized_url in used_urls:
                continue
            
            image_data = {
                'url': optimized_url,
                'photographer': photo['user']['name'],
                'photographer_url': photo['user']['links']['html']
            }
            accumulated_images.append(image_data)
            used_photo_ids.add(photo_id)
            used_urls.add(optimized_url)
    
    if accumulated_images:
        try:
            db.execute('BEGIN TRANSACTION')
            db.execute('DELETE FROM image_cache WHERE query = ?', (query,))
            
            for idx, image_data in enumerate(accumulated_images):
                db.execute('''INSERT INTO image_cache 
                             (query, image_index, image_url, photographer, photographer_url) 
                             VALUES (?, ?, ?, ?, ?)''',
                          (query, idx, image_data['url'], image_data['photographer'], 
                           image_data['photographer_url']))
            
            db.commit()
        except Exception as e:
            db.rollback()
            app.logger.error(f"Failed to update cache atomically: {e}")
            app.logger.info("Keeping previous cache intact")
    
    if len(accumulated_images) < count:
        fallback_needed = count - len(accumulated_images)
        fallbacks = get_fallback_images(query, fallback_needed)
        
        for fallback in fallbacks:
            if fallback['url'] not in [img['url'] for img in accumulated_images]:
                accumulated_images.append(fallback)
                if len(accumulated_images) >= count:
                    break
        
        app.logger.info(f"Padded {len(accumulated_images) - (count - fallback_needed)} fallback images to meet count requirement")
    
    db.close()
    return accumulated_images[:count]

def get_fallback_images(query, count=1):
    query_lower = query.lower()
    
    destination_types = {
        'nature': ['mountain', 'hill', 'peak', 'summit', 'valley', 'meadow', 'forest', 'woods', 'jungle', 
                   'trail', 'hike', 'trekking', 'nature', 'wildlife', 'national park', 'reserve'],
        'water': ['beach', 'ocean', 'sea', 'bay', 'gulf', 'lake', 'pond', 'river', 'stream', 'waterfall', 
                  'falls', 'coast', 'shore', 'island', 'archipelago', 'marina', 'harbor'],
        'urban': ['city', 'town', 'skyline', 'downtown', 'metropolitan', 'building', 'architecture', 
                  'skyscraper', 'tower', 'plaza', 'square', 'street', 'avenue', 'boulevard', 'urban'],
        'heritage': ['temple', 'church', 'mosque', 'monastery', 'shrine', 'cathedral', 'palace', 'castle', 
                     'fort', 'fortress', 'monument', 'memorial', 'ruins', 'heritage', 'historical', 
                     'ancient', 'archaeological', 'unesco'],
        'desert': ['desert', 'dune', 'sand', 'arid', 'oasis', 'sahara', 'canyon', 'badlands'],
        'scenic': ['landscape', 'scenic', 'panorama', 'view', 'vista', 'lookout', 'viewpoint', 
                   'picturesque', 'countryside', 'rural']
    }
    
    all_fallback_urls = {
        'nature': [
            'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?auto=format&q=80&w=1200',
            'https://images.unsplash.com/photo-1511593358241-7eea1f3c84e5?auto=format&q=80&w=1200',
            'https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?auto=format&q=80&w=1200',
            'https://images.unsplash.com/photo-1501785888041-af3ef285b470?auto=format&q=80&w=1200'
        ],
        'water': [
            'https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&q=80&w=1200',
            'https://images.unsplash.com/photo-1505142468610-359e7d316be0?auto=format&q=80&w=1200',
            'https://images.unsplash.com/photo-1559827260-dc66d52bef19?auto=format&q=80&w=1200',
            'https://images.unsplash.com/photo-1544551763-46a013bb70d5?auto=format&q=80&w=1200'
        ],
        'urban': [
            'https://images.unsplash.com/photo-1480714378408-67cf0d13bc1b?auto=format&q=80&w=1200',
            'https://images.unsplash.com/photo-1514565131-fce0801e5785?auto=format&q=80&w=1200',
            'https://images.unsplash.com/photo-1477959858617-67f85cf4f1df?auto=format&q=80&w=1200',
            'https://images.unsplash.com/photo-1449824913935-59a10b8d2000?auto=format&q=80&w=1200'
        ],
        'heritage': [
            'https://images.unsplash.com/photo-1548013146-72479768bada?auto=format&q=80&w=1200',
            'https://images.unsplash.com/photo-1524492412937-b28074a5d7da?auto=format&q=80&w=1200',
            'https://images.unsplash.com/photo-1564507592333-c60657eea523?auto=format&q=80&w=1200',
            'https://images.unsplash.com/photo-1512428559087-560fa5ceab42?auto=format&q=80&w=1200'
        ],
        'desert': [
            'https://images.unsplash.com/photo-1509316785289-025f5b846b35?auto=format&q=80&w=1200',
            'https://images.unsplash.com/photo-1473580044384-7ba9967e16a0?auto=format&q=80&w=1200',
            'https://images.unsplash.com/photo-1547036967-23d11aacaee0?auto=format&q=80&w=1200',
            'https://images.unsplash.com/photo-1682687220742-aba13b6e50ba?auto=format&q=80&w=1200'
        ],
        'scenic': [
            'https://images.unsplash.com/photo-1469854523086-cc02fe5d8800?auto=format&q=80&w=1200',
            'https://images.unsplash.com/photo-1476514525535-07fb3b4ae5f1?auto=format&q=80&w=1200',
            'https://images.unsplash.com/photo-1530789253388-582c481c54b0?auto=format&q=80&w=1200',
            'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?auto=format&q=80&w=1200'
        ]
    }
    
    scores = {dest_type: 0 for dest_type in destination_types.keys()}
    
    for dest_type, keywords in destination_types.items():
        for keyword in keywords:
            if keyword in query_lower:
                scores[dest_type] += 1
    
    sorted_types = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    matched_type = sorted_types[0][0] if sorted_types[0][1] > 0 else 'scenic'
    
    result_images = []
    used_urls = set()
    
    primary_urls = all_fallback_urls.get(matched_type, all_fallback_urls['scenic'])
    for url in primary_urls:
        if url not in used_urls:
            result_images.append({
                'url': url,
                'photographer': 'Unsplash',
                'photographer_url': 'https://unsplash.com'
            })
            used_urls.add(url)
            if len(result_images) >= count:
                return result_images
    
    for dest_type, _ in sorted_types:
        if dest_type != matched_type:
            for url in all_fallback_urls.get(dest_type, []):
                if url not in used_urls:
                    result_images.append({
                        'url': url,
                        'photographer': 'Unsplash',
                        'photographer_url': 'https://unsplash.com'
                    })
                    used_urls.add(url)
                    if len(result_images) >= count:
                        return result_images
    
    return result_images[:count] if result_images else [{
        'url': 'https://images.unsplash.com/photo-1469854523086-cc02fe5d8800?auto=format&q=80&w=1200',
        'photographer': 'Unsplash',
        'photographer_url': 'https://unsplash.com'
    }]

@app.route('/api/fetch-destination-image', methods=['POST'])
@login_required
def fetch_destination_image():
    try:
        data = request.get_json()
        destination = data.get('destination', '')
        
        if not destination:
            return jsonify({'success': False, 'message': 'Destination required'}), 400
        
        images = fetch_unsplash_images(f"{destination} landmark tourist attraction", 1)
        
        if images:
            return jsonify({'success': True, 'image': images[0]}), 200
        else:
            return jsonify({'success': False, 'message': 'No images found'}), 404
            
    except Exception as e:
        app.logger.error(f"Fetch destination image error: {e}")
        return jsonify({'success': False, 'message': 'An error occurred'}), 500

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
