from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
from datetime import datetime
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.urandom(24)  # More secure secret key

# Configure upload folders
CATEGORY_UPLOAD_FOLDER = os.path.join('static', 'images', 'categories')
DESTINATION_UPLOAD_FOLDER = os.path.join('static', 'images', 'destinations')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['CATEGORY_UPLOAD_FOLDER'] = CATEGORY_UPLOAD_FOLDER
app.config['DESTINATION_UPLOAD_FOLDER'] = DESTINATION_UPLOAD_FOLDER

# Create upload folders if they don't exist
os.makedirs(CATEGORY_UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DESTINATION_UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# Database connection
def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# Initialize database
def init_db():
    with get_db_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                image_path TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS destinations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category_id INTEGER NOT NULL,
                location TEXT NOT NULL,
                description TEXT,
                price REAL,
                photo TEXT,
                FOREIGN KEY (category_id) REFERENCES categories(id)
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS couples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                wedding_date TEXT,
                password TEXT NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                couple_id INTEGER NOT NULL,
                destination_id INTEGER NOT NULL,
                booking_date TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                FOREIGN KEY (couple_id) REFERENCES couples(id),
                FOREIGN KEY (destination_id) REFERENCES destinations(id)
            )
        ''')
        conn.commit()

# Homepage
@app.route('/')
def index():
    with get_db_connection() as conn:
        categories = conn.execute('SELECT * FROM categories LIMIT 3').fetchall()
        destinations = conn.execute('''
            SELECT d.*, c.name as category_name 
            FROM destinations d
            JOIN categories c ON d.category_id = c.id
            LIMIT 3
        ''').fetchall()
    return render_template('index.html', categories=categories, featured_destinations=destinations)

@app.context_processor
def inject_now():
    return {'now': datetime.now()}

# ADMIN SECTION --------------------------------------------------------

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form['username'] == 'admin' and request.form['password'] == 'admin123':
            session['admin_username'] = 'admin'
            flash('Login successful!', 'success')
            return redirect(url_for('admin_dashboard'))
        flash('Invalid credentials', 'danger')
    return render_template('admin/login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'admin_username' not in session:
        return redirect(url_for('admin_login'))
    
    with get_db_connection() as conn:
        # Get all categories with their image paths
        categories = conn.execute('SELECT * FROM categories').fetchall()
        
        # Get all destinations with their category names
        destinations = conn.execute('''
            SELECT d.*, c.name as category_name 
            FROM destinations d
            JOIN categories c ON d.category_id = c.id
        ''').fetchall()
        
        # Get all registered couples
        couples = conn.execute('SELECT * FROM couples').fetchall()
        
        # Get recent bookings (optional)
        recent_bookings = conn.execute('''
            SELECT b.*, c.name as couple_name, d.name as destination_name
            FROM bookings b
            JOIN couples c ON b.couple_id = c.id
            JOIN destinations d ON b.destination_id = d.id
            ORDER BY b.booking_date DESC LIMIT 5
        ''').fetchall()
    
    return render_template('admin/dashboard.html', 
                         categories=categories,
                         destinations=destinations,
                         couples=couples,
                         recent_bookings=recent_bookings)

@app.route('/admin/couples/view/<int:id>')
def admin_view_couple(id):
    if 'admin_username' not in session:
        return redirect(url_for('admin_login'))
    
    with get_db_connection() as conn:
        couple = conn.execute('SELECT * FROM couples WHERE id = ?', (id,)).fetchone()
        if not couple:
            flash('Couple not found', 'danger')
            return redirect(url_for('admin_dashboard'))
        
        # Get couple's bookings
        bookings = conn.execute('''
            SELECT b.*, d.name as destination_name
            FROM bookings b
            JOIN destinations d ON b.destination_id = d.id
            WHERE b.couple_id = ?
            ORDER BY b.booking_date DESC
        ''', (id,)).fetchall()
    
    return render_template('admin/view_couple.html', 
                         couple=couple,
                         bookings=bookings)

@app.route('/admin/couples/delete/<int:id>', methods=['POST'])
def admin_delete_couple(id):
    if 'admin_username' not in session:
        return redirect(url_for('admin_login'))
    
    with get_db_connection() as conn:
        # Check if couple has bookings first
        bookings = conn.execute('SELECT id FROM bookings WHERE couple_id = ?', (id,)).fetchall()
        
        if bookings:
            flash('Cannot delete couple with existing bookings', 'danger')
            return redirect(url_for('admin_dashboard'))
            
        conn.execute('DELETE FROM couples WHERE id = ?', (id,))
        conn.commit()
    
    flash('Couple deleted successfully', 'success')
    return redirect(url_for('admin_dashboard'))

# CATEGORY MANAGEMENT ------------------------------------------------

@app.route('/admin/categories')
def manage_categories():
    if 'admin_username' not in session:
        return redirect(url_for('admin_login'))
    
    with get_db_connection() as conn:
        categories = conn.execute('''
            SELECT c.*, COUNT(d.id) as destination_count
            FROM categories c
            LEFT JOIN destinations d ON c.id = d.category_id
            GROUP BY c.id
        ''').fetchall()
    
    return render_template('admin/manage_categories.html', categories=categories)

@app.route('/admin/categories/add', methods=['GET', 'POST'])
def add_category():
    if 'admin_username' not in session:
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        name = request.form['name'].strip()
        image_option = request.form.get('image_option')
        
        image_path = ''
        if image_option == 'upload' and 'image_file' in request.files:
            file = request.files['image_file']
            if file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['CATEGORY_UPLOAD_FOLDER'], filename)
                file.save(filepath)
                image_path = filename  # Store only filename, not full path
        elif image_option == 'url':
            image_path = request.form.get('image_url', '').strip()

        if not name:
            flash('Category name is required', 'danger')
        else:
            try:
                conn = get_db_connection()
                conn.execute('INSERT INTO categories (name, image_path) VALUES (?, ?)',
                           (name, image_path))
                conn.commit()
                flash('Category added successfully!', 'success')
                return redirect(url_for('manage_categories'))
            except sqlite3.IntegrityError:
                flash('Category name already exists', 'danger')
            finally:
                conn.close()

    return render_template('admin/add_category.html')

@app.route('/admin/categories/edit/<int:id>', methods=['GET', 'POST'])
def edit_category(id):
    if 'admin_username' not in session:
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    category = conn.execute('SELECT * FROM categories WHERE id = ?', (id,)).fetchone()
    
    if not category:
        conn.close()
        flash('Category not found', 'danger')
        return redirect(url_for('manage_categories'))

    if request.method == 'POST':
        name = request.form['name'].strip()
        image_action = request.form.get('image_action', 'keep')
        
        # Handle image based on selected action
        image_path = category['image_path'] if image_action == 'keep' else ''
        
        if image_action == 'upload' and 'image_file' in request.files:
            file = request.files['image_file']
            if file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['CATEGORY_UPLOAD_FOLDER'], filename)  # Changed to CATEGORY_UPLOAD_FOLDER
                file.save(filepath)
                image_path = filename  # Store only filename
        elif image_action == 'url':
            image_path = request.form.get('image_url', '').strip()
        elif image_action == 'remove':
            image_path = ''
        
        try:
            conn.execute('UPDATE categories SET name = ?, image_path = ? WHERE id = ?',
                        (name, image_path, id))
            conn.commit()
            flash('Category updated successfully!', 'success')
            return redirect(url_for('manage_categories'))
        except sqlite3.IntegrityError:
            flash('Category name already exists', 'danger')
        finally:
            conn.close()
    
    return render_template('admin/edit_category.html', category=category)

@app.route('/admin/categories/delete/<int:id>', methods=['POST'])
def delete_category(id):
    if 'admin_username' not in session:
        return redirect(url_for('admin_login'))
    
    with get_db_connection() as conn:
        # Check if category is used by any destinations
        destinations = conn.execute('SELECT id FROM destinations WHERE category_id = ?', (id,)).fetchall()
        if destinations:
            flash('Cannot delete category with associated destinations', 'danger')
            return redirect(url_for('manage_categories'))
        
        conn.execute('DELETE FROM categories WHERE id = ?', (id,))
        conn.commit()
    flash('Category deleted successfully', 'success')
    return redirect(url_for('manage_categories'))

# DESTINATION MANAGEMENT ---------------------------------------------

@app.route('/admin/destinations')
def manage_destinations():
    if 'admin_username' not in session:
        return redirect(url_for('admin_login'))

    with get_db_connection() as conn:
        destinations = conn.execute('''
            SELECT d.*, c.name as category_name 
            FROM destinations d
            JOIN categories c ON d.category_id = c.id
            ORDER BY d.name
        ''').fetchall()
    
    return render_template('admin/manage_destinations.html', destinations=destinations)

@app.route('/admin/destinations/add', methods=['GET', 'POST'])
def add_destination():
    if 'admin_username' not in session:
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    categories = conn.execute('SELECT * FROM categories').fetchall()

    if request.method == 'POST':
        try:
            # Get form data
            name = request.form['name'].strip()
            category_id = request.form['category_id']
            location = request.form['location'].strip()
            description = request.form['description'].strip()
            price = float(request.form['price'])
            
            # Handle file upload
            photo = ''
            if 'photo' in request.files:
                file = request.files['photo']
                if file.filename != '' and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(app.config['DESTINATION_UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    photo = filename  # Store only filename, not full path

            # Insert into database
            conn.execute('''
                INSERT INTO destinations (name, category_id, location, description, price, photo)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (name, category_id, location, description, price, photo))
            conn.commit()
            flash('Destination added successfully!', 'success')
            return redirect(url_for('manage_destinations'))
        except Exception as e:
            conn.rollback()
            flash(f'Error adding destination: {str(e)}', 'danger')
        finally:
            conn.close()

    return render_template('admin/add_destination.html', categories=categories)

@app.route('/admin/destinations/edit/<int:id>', methods=['GET', 'POST'])
def edit_destination(id):
    if 'admin_username' not in session:
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    
    # Get existing destination
    destination = conn.execute('SELECT * FROM destinations WHERE id = ?', (id,)).fetchone()
    categories = conn.execute('SELECT * FROM categories').fetchall()
    
    if not destination:
        conn.close()
        flash('Destination not found', 'danger')
        return redirect(url_for('manage_destinations'))

    if request.method == 'POST':
        name = request.form['name'].strip()
        category_id = request.form['category_id']
        location = request.form['location'].strip()
        description = request.form['description'].strip()
        price = float(request.form['price'])
        image_action = request.form.get('image_action', 'keep')
        
        # Handle image based on selected action
        photo = destination['photo']
        if image_action == 'upload' and 'image_file' in request.files:
            file = request.files['image_file']
            if file.filename != '':
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['DESTINATION_UPLOAD_FOLDER'], 'destinations', filename)
                file.save(filepath)
                photo = filename
        elif image_action == 'url':
            photo = request.form.get('image_url', '').strip()

        try:
            conn.execute('''
                UPDATE destinations 
                SET name = ?, category_id = ?, location = ?, 
                    description = ?, price = ?, photo = ?
                WHERE id = ?
            ''', (name, category_id, location, description, price, photo, id))
            conn.commit()
            flash('Destination updated successfully!', 'success')
            return redirect(url_for('manage_destinations'))
        except Exception as e:
            conn.rollback()
            flash(f'Error updating destination: {str(e)}', 'danger')
        finally:
            conn.close()
    
    return render_template('admin/edit_destination.html', 
                         destination=destination,
                         categories=categories)
                         
@app.route('/admin/destinations/delete/<int:id>', methods=['POST'])
def admin_delete_destination(id):
    if 'admin_username' not in session:
        return redirect(url_for('admin_login'))
    
    with get_db_connection() as conn:
        # Check if destination has bookings
        bookings = conn.execute('SELECT id FROM bookings WHERE destination_id = ?', (id,)).fetchall()
        if bookings:
            flash('Cannot delete destination with existing bookings', 'danger')
            return redirect(url_for('manage_destinations'))
        
        conn.execute('DELETE FROM destinations WHERE id = ?', (id,))
        conn.commit()
    flash('Destination deleted successfully', 'success')
    return redirect(url_for('manage_destinations'))

# COUPLE SECTION ------------------------------------------------------

@app.route('/couple/register', methods=['GET', 'POST'])
def couple_register():
    if request.method == 'POST':
        name = request.form['name'].strip()
        email = request.form['email'].strip()
        wedding_date = request.form.get('wedding_date', '')
        password = request.form['password']
        
        if not all([name, email, password]):
            flash('All fields are required', 'danger')
            return redirect(url_for('couple_register'))
        
        try:
            with get_db_connection() as conn:
                conn.execute('''
                    INSERT INTO couples (name, email, wedding_date, password)
                    VALUES (?, ?, ?, ?)
                ''', (name, email, wedding_date, password))
                conn.commit()
                session['couple_email'] = email
                flash('Registration successful!', 'success')
                return redirect(url_for('couple_dashboard'))
        except sqlite3.IntegrityError:
            flash('Email already registered', 'danger')
    
    return render_template('couple/register.html')

@app.route('/couple/login', methods=['GET', 'POST'])
def couple_login():
    if request.method == 'POST':
        email = request.form['email'].strip()
        password = request.form['password']
        
        with get_db_connection() as conn:
            couple = conn.execute('''
                SELECT * FROM couples WHERE email = ? AND password = ?
            ''', (email, password)).fetchone()
        
        if couple:
            session['couple_email'] = email
            flash('Login successful!', 'success')
            return redirect(url_for('couple_dashboard'))
        flash('Invalid email or password', 'danger')
    
    return render_template('couple/login.html')

@app.route('/couple/dashboard')
def couple_dashboard():
    if 'couple_email' not in session:
        return redirect(url_for('couple_login'))
    
    with get_db_connection() as conn:
        couple = conn.execute('SELECT * FROM couples WHERE email = ?', 
                            (session['couple_email'],)).fetchone()
        if not couple:
            session.pop('couple_email', None)
            return redirect(url_for('couple_login'))
        
        bookings = conn.execute('''
            SELECT b.*, d.name as destination_name, d.photo as destination_photo
            FROM bookings b
            JOIN destinations d ON b.destination_id = d.id
            WHERE b.couple_id = ?
            ORDER BY b.booking_date DESC
        ''', (couple['id'],)).fetchall()
    
    return render_template('couple/dashboard.html', couple=couple, bookings=bookings)

# PUBLIC PAGES -------------------------------------------------------

@app.route('/categories')
def browse_categories():
    with get_db_connection() as conn:
        categories = conn.execute('SELECT * FROM categories').fetchall()
    return render_template('categories/browse.html', categories=categories)

@app.route('/category/<int:category_id>')
def category_destinations(category_id):
    with get_db_connection() as conn:
        category = conn.execute('SELECT * FROM categories WHERE id = ?', (category_id,)).fetchone()
        if not category:
            flash('Category not found', 'danger')
            return redirect(url_for('index'))
        
        destinations = conn.execute('''
            SELECT * FROM destinations 
            WHERE category_id = ?
        ''', (category_id,)).fetchall()
    
    return render_template('destinations/list.html', 
                         category=category,
                         destinations=destinations)

@app.route('/destination/<int:destination_id>')
def destination_details(destination_id):
    with get_db_connection() as conn:
        destination = conn.execute('''
            SELECT d.*, c.name as category_name
            FROM destinations d
            JOIN categories c ON d.category_id = c.id
            WHERE d.id = ?
        ''', (destination_id,)).fetchone()
        
        if not destination:
            flash('Destination not found', 'danger')
            return redirect(url_for('index'))
        
        # Check if logged-in couple has booked this destination
        booked = False
        if 'couple_email' in session:
            couple = conn.execute('SELECT id FROM couples WHERE email = ?', 
                                 (session['couple_email'],)).fetchone()
            if couple:
                booking = conn.execute('''
                    SELECT id FROM bookings 
                    WHERE couple_id = ? AND destination_id = ?
                ''', (couple['id'], destination_id)).fetchone()
                booked = bool(booking)
    
    return render_template('destinations/detail.html', 
                         destination=destination,
                         booked=booked)


# BOOKING SYSTEM -----------------------------------------------------

@app.route('/book/<int:destination_id>', methods=['POST'])
def book_destination(destination_id):
    if 'couple_email' not in session:
        flash('Please login to book a destination', 'danger')
        return redirect(url_for('couple_login'))

    wedding_date = request.form['wedding_date']
    if not wedding_date:
        flash('Please select a wedding date', 'danger')
        return redirect(url_for('destination_details', destination_id=destination_id))

    with get_db_connection() as conn:
        # Get couple ID
        couple = conn.execute('SELECT id FROM couples WHERE email = ?', 
                            (session['couple_email'],)).fetchone()
        
        # Check for existing booking
        existing = conn.execute('''
            SELECT id FROM bookings 
            WHERE couple_id = ? AND destination_id = ? AND booking_date = ?
        ''', (couple['id'], destination_id, wedding_date)).fetchone()
        
        if existing:
            flash('You already have a booking for this date', 'warning')
            return redirect(url_for('destination_details', destination_id=destination_id))
        
        # Create booking
        conn.execute('''
            INSERT INTO bookings (couple_id, destination_id, booking_date, status)
            VALUES (?, ?, ?, ?)
        ''', (couple['id'], destination_id, wedding_date, 'pending'))
        conn.commit()
    
    flash('Booking successful!', 'success')
    return redirect(url_for('couple_dashboard'))

@app.route('/couple/bookings')  # Fixed typo "couple" (was "couple")
def couple_bookings():
    if 'couple_email' not in session:
        return redirect(url_for('couple_login'))
    
    with get_db_connection() as conn:
        couple = conn.execute('SELECT id FROM couples WHERE email = ?', 
                            (session['couple_email'],)).fetchone()
        bookings = conn.execute('''
            SELECT b.*, d.name as destination_name, d.photo as destination_photo
            FROM bookings b
            JOIN destinations d ON b.destination_id = d.id
            WHERE b.couple_id = ?
            ORDER BY b.booking_date DESC
        ''', (couple['id'],)).fetchall()
    
    return render_template('couple/bookings.html', bookings=bookings)

# ADMIN BOOKING MANAGEMENT -------------------------------------------

@app.route('/admin/bookings')
def admin_bookings():
    if 'admin_username' not in session:
        return redirect(url_for('admin_login'))
    
    with get_db_connection() as conn:
        bookings = conn.execute('''
            SELECT b.*, c.name as couple_name, d.name as destination_name
            FROM bookings b
            JOIN couples c ON b.couple_id = c.id
            JOIN destinations d ON b.destination_id = d.id
            ORDER BY b.booking_date DESC
        ''').fetchall()
    
    return render_template('admin/bookings.html', bookings=bookings)

@app.route('/admin/bookings/approve/<int:booking_id>')
def approve_booking(booking_id):
    if 'admin_username' not in session:
        abort(403)
    
    try:
        with get_db_connection() as conn:
            # Verify booking exists
            booking = conn.execute('SELECT id FROM bookings WHERE id = ?', 
                                 (booking_id,)).fetchone()
            if not booking:
                flash('Booking not found', 'error')
                return redirect(url_for('admin_bookings'))
            
            # Update status
            conn.execute('UPDATE bookings SET status = "approved" WHERE id = ?', 
                       (booking_id,))
            conn.commit()
            
            # Verify update
            updated = conn.execute('SELECT status FROM bookings WHERE id = ?',
                                 (booking_id,)).fetchone()
            print(f"Updated status: {updated['status']}")  # Debug
            
        flash('Booking approved', 'success')
    except Exception as e:
        print(f"Approval error: {e}")
        flash('Approval failed', 'error')
    
    return redirect(url_for('admin_bookings'))
    

@app.route('/admin/bookings/reject/<int:booking_id>')
def reject_booking(booking_id):
    if 'admin_username' not in session:
        return redirect(url_for('admin_login'))
    
    with get_db_connection() as conn:
        conn.execute('DELETE FROM bookings WHERE id = ?', (booking_id,))
        conn.commit()
    flash('Booking rejected', 'success')
    return redirect(url_for('admin_bookings'))

# AUTHENTICATION -----------------------------------------------------

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

# INITIALIZATION ----------------------------------------------------

if __name__ == '__main__':
    init_db()
    app.run(debug=True)