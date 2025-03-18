from flask import Flask, request, render_template, redirect, url_for, flash, session
import sqlite3
from datetime import datetime
import random
import os
from os.path import basename
from versionrunner import *

app = Flask(__name__)
app.secret_key = "secret_key"  # Key for session encryption (should be changed to a stronger key in practice)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.static_folder = 'uploads'

# Register basename filter
app.jinja_env.filters['basename'] = basename

# Database initialization
def init_db():
    conn = sqlite3.connect("sharing_platform.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, age INTEGER, region TEXT, username TEXT UNIQUE, password TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS posts 
                 (id INTEGER PRIMARY KEY, user_id INTEGER, content TEXT, file_path TEXT, 
                  end_time TEXT, region TEXT, apply_number INTEGER UNIQUE, box_number INTEGER)''')  # Added box_number and UNIQUE constraint
    c.execute('''CREATE TABLE IF NOT EXISTS applications 
                 (id INTEGER PRIMARY KEY, post_id INTEGER, user_id INTEGER, apply_date TEXT)''')
    conn.commit()
    conn.close()

# Check and remove expired posts (including file deletion)
def remove_expired_posts():
    try:
        conn = sqlite3.connect("sharing_platform.db")
        c = conn.cursor()
        current_time = datetime.now().strftime("%Y-%m-%dT%H:%M")
        
        c.execute("SELECT id, file_path FROM posts WHERE end_time < ?", (current_time,))
        expired_posts = c.fetchall()
        
        for post_id, file_path in expired_posts:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    print(f"Deleted file: {file_path}")
                except Exception as e:
                    print(f"File deletion error: {e}")
            c.execute("DELETE FROM applications WHERE post_id = ?", (post_id,))
            c.execute("DELETE FROM posts WHERE id = ?", (post_id,))
            print(f"Deleted post ID: {post_id}")
        
        conn.commit()
        conn.close()
        return len(expired_posts)
    except Exception as e:
        print(f"Error occurred while deleting posts: {e}")
        return 0

# Login page
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = sqlite3.connect("sharing_platform.db")
        c = conn.cursor()
        c.execute("SELECT id, name, age, region FROM users WHERE username = ? AND password = ?", (username, password))
        user = c.fetchone()
        conn.close()
        
        if user:
            session['user_id'] = user[0]  # Store user_id in session
            flash("Login successful!")
            return redirect(url_for('home'))
        else:
            flash("Incorrect username or password.")
    return render_template('login.html')

# Logout
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash("You have been logged out.")
    return redirect(url_for('login'))

# Home page
@app.route('/', methods=['GET', 'POST'])
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    removed_count = remove_expired_posts()
    if removed_count > 0:
        flash(f"{removed_count} expired posts have been automatically deleted.")
    
    conn = sqlite3.connect("sharing_platform.db")
    c = conn.cursor()
    
    # Get filter values
    city = request.form.get('city', '')
    district = request.form.get('district', '')
    road = request.form.get('road', '')
    
    # Base query
    query = """
        SELECT posts.id, posts.content, posts.file_path, posts.end_time, 
               posts.region, posts.apply_number, users.name, posts.user_id 
        FROM posts 
        JOIN users ON posts.user_id = users.id
        WHERE 1=1
    """
    params = []
    
    # Apply filters
    if city:
        query += " AND posts.region LIKE ?"
        params.append(f"%{city}%")
    if district:
        query += " AND posts.region LIKE ?"
        params.append(f"%{district}%")
    if road:
        query += " AND posts.region LIKE ?"
        params.append(f"%{road}%")
    
    c.execute(query, params)
    posts = c.fetchall()
    
    c.execute("SELECT post_id FROM applications")
    applied_posts = [row[0] for row in c.fetchall()]
    
    user_id = session['user_id']
    c.execute("SELECT name, age, region FROM users WHERE id = ?", (user_id,))
    user_info = c.fetchone()
    
    # Retrieve posts applied by the user (including box number)
    c.execute("""
        SELECT p.id, p.content, p.apply_number, p.box_number
        FROM posts p
        JOIN applications a ON p.id = a.post_id
        WHERE a.user_id = ?
    """, (session['user_id'],))
    applied_items = c.fetchall()
    
    # Retrieve list of applied posts
    c.execute("SELECT post_id FROM applications")
    applied_posts = [row[0] for row in c.fetchall()]
    
    user_id = session['user_id']
    c.execute("SELECT name, age, region FROM users WHERE id = ?", (user_id,))
    user_info = c.fetchone()
    
    conn.close()
    
    return render_template('home.html', posts=posts, applied_posts=applied_posts, 
                           user_info=user_info, applied_items=applied_items, user_id=user_id,
                           selected_city=city, selected_district=district, selected_road=road)

# Registration
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        age = request.form['age']
        region = request.form['region']
        username = request.form['username']
        password = request.form['password']
        
        conn = sqlite3.connect("sharing_platform.db")
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (name, age, region, username, password) VALUES (?, ?, ?, ?, ?)", 
                      (name, age, region, username, password))
            conn.commit()
            flash("Registration completed! Please log in.")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("Username already exists.")
        finally:
            conn.close()
    return render_template('register.html')

# Create post
@app.route('/create_post', methods=['GET', 'POST'])
def create_post():
    if 'user_id' not in session:
        flash("Please log in first!")
        return redirect(url_for('login'))
    
    remove_expired_posts()
    user_id = session['user_id']
    
    conn = sqlite3.connect("sharing_platform.db")
    c = conn.cursor()
    
    # Retrieve currently used box numbers
    current_time = datetime.now().strftime("%Y-%m-%dT%H:%M")
    
    # Retrieve used box numbers
    c.execute("SELECT box_number FROM posts WHERE end_time > ?", (current_time,))
    used_boxes = [row[0] for row in c.fetchall() if row[0] is not None]
    print(f"Used boxes: {used_boxes}")
    
    # Calculate available box numbers
    all_boxes = {1, 2, 3, 4}
    available_boxes = sorted(list(all_boxes - set(used_boxes)))
    if not used_boxes:  # If no posts exist, all boxes are available
        available_boxes = [1, 2, 3, 4]
    print(f"Available boxes: {available_boxes}")
    
    if request.method == 'POST':
        content = request.form['content']
        end_time = request.form['end_time']
        box_number = request.form['box_number']  # Receive box number
        print(box_number)
        file = request.files['file']
        
        # Validate box number
        if int(box_number) not in available_boxes:
            conn.close()
            flash("The selected box is already in use! Please choose another box.")
            return redirect(url_for('create_post'))
        
        while True:
            apply_number = random.randint(1000, 9999)
            c.execute("SELECT COUNT(*) FROM posts WHERE apply_number = ?", (apply_number,))
            if c.fetchone()[0] == 0:  # Exit loop if no duplicate
                break
            
        c.execute("SELECT name, region FROM users WHERE id = ?", (user_id,))
        user_data = c.fetchone()
        user_name, region = user_data[0], user_data[1]
        
        file_path = None
        if file:
            filename, ext = os.path.splitext(file.filename)
            new_filename = f"{filename}_{user_name}_{end_time.replace(':', '-')}{ext}"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
            file.save(file_path)
        
        # Insert box_number into posts table
        c.execute("""
            INSERT INTO posts (user_id, content, file_path, end_time, region, apply_number, box_number)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, content, file_path, end_time, region, apply_number, box_number))
        conn.commit()
        conn.close()
        
        flash("Post has been created!")
        return redirect(url_for('home'))
    
    return render_template('create_post.html', available_boxes=available_boxes)

# Apply function
@app.route('/apply/<int:post_id>', methods=['GET', 'POST'])
def apply(post_id):
    if 'user_id' not in session:
        flash("Please log in first!")
        return redirect(url_for('login'))
    
    remove_expired_posts()
    user_id = session['user_id']
    today_date = datetime.now().strftime("%Y-%m-%d")
    
    conn = sqlite3.connect("sharing_platform.db")
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM applications WHERE user_id = ? AND apply_date = ?", (user_id, today_date))
    apply_count = c.fetchone()[0]
    if apply_count >= 2:
        flash("You can only apply for up to 2 posts per day!")
        conn.close()
        return redirect(url_for('home'))
    
    c.execute("SELECT * FROM applications WHERE post_id = ?", (post_id,))
    if c.fetchone():
        flash("Someone has already applied for this!")
        conn.close()
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        c.execute("INSERT INTO applications (post_id, user_id, apply_date) VALUES (?, ?, ?)", 
                  (post_id, user_id, today_date))
        c.execute("SELECT apply_number FROM posts WHERE id = ?", (post_id,))
        apply_number = c.fetchone()[0]
        conn.commit()
        conn.close()
        flash(f"Application completed! Number: {apply_number}")
        return redirect(url_for('home'))
    
    conn.close()
    return render_template('apply.html', post_id=post_id)

# Edit user profile
@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    if 'user_id' not in session:
        flash("Please log in first!")
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    conn = sqlite3.connect("sharing_platform.db")
    c = conn.cursor()
    
    c.execute("SELECT name, age, region FROM users WHERE id = ?", (user_id,))
    user_info = c.fetchone()
    
    if request.method == 'POST':
        name = request.form['name']
        age = request.form['age']
        region = request.form['region']
        
        c.execute("UPDATE users SET name = ?, age = ?, region = ? WHERE id = ?", 
                  (name, age, region, user_id))
        conn.commit()
        conn.close()
        flash("User information has been updated!")
        return redirect(url_for('home'))
    
    conn.close()
    return render_template('edit_profile.html', user_info=user_info)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return app.send_static_file(filename)

if __name__ == '__main__':
    search_version(__file__)
    if not os.path.exists("uploads"):
        os.makedirs("uploads")
    init_db()
    print("Checking for expired posts...")
    removed_count = remove_expired_posts()
    app.run(host='0.0.0.0', debug=True)