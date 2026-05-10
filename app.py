from flask import Flask, render_template, request, redirect, url_for, session, abort
from flask_session import Session
import sqlite3
import hashlib
import os
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'pulse_secret_key_2024'
app.config['SESSION_TYPE'] = 'filesystem'
app.config['UPLOAD_FOLDER'] = 'static/avatars'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

Session(app)

def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def get_db():
    conn = sqlite3.connect('pulse.db')
    conn.row_factory = sqlite3.Row
    return conn

def time_ago(timestamp):
    """Преобразует timestamp в формат 'X time ago'"""
    now = datetime.now()
    diff = now - datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
    
    if diff.days > 365:
        return f"{diff.days // 365} year{'s' if diff.days // 365 > 1 else ''} ago"
    elif diff.days > 30:
        return f"{diff.days // 30} month{'s' if diff.days // 30 > 1 else ''} ago"
    elif diff.days > 0:
        return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
    elif diff.seconds > 3600:
        return f"{diff.seconds // 3600} hour{'s' if diff.seconds // 3600 > 1 else ''} ago"
    elif diff.seconds > 60:
        return f"{diff.seconds // 60} minute{'s' if diff.seconds // 60 > 1 else ''} ago"
    else:
        return "just now"

def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            avatar TEXT DEFAULT '',
            bio TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            user_id INTEGER,
            likes INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS likes (
            user_id INTEGER,
            post_id INTEGER,
            PRIMARY KEY (user_id, post_id)
        );
    ''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db()
    rows = conn.execute('''
        SELECT posts.*, users.username, users.avatar 
        FROM posts 
        JOIN users ON posts.user_id = users.id 
        ORDER BY posts.created_at DESC
    ''').fetchall()
    
    posts = []
    for row in rows:
        post = {
            'id': row['id'],
            'content': row['content'],
            'user_id': row['user_id'],
            'likes': row['likes'],
            'created_at': row['created_at'],
            'created_ago': time_ago(row['created_at']),
            'username': row['username'],
            'avatar': row['avatar'] if row['avatar'] else None,
            'liked': conn.execute('SELECT 1 FROM likes WHERE user_id = ? AND post_id = ?', 
                                  (session['user_id'], row['id'])).fetchone() is not None
        }
        posts.append(post)
    
    conn.close()
    return render_template('index.html', posts=posts)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = hash_password(request.form['password'])
        conn = get_db()
        try:
            conn.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))
            conn.commit()
            return redirect(url_for('login'))
        except:
            return render_template('register.html', error='Username already exists')
        finally:
            conn.close()
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = hash_password(request.form['password'])
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password)).fetchone()
        conn.close()
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('index'))
        return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/logout_confirm')
def logout_confirm():
    return render_template('logout_confirm.html')

@app.route('/create_post', methods=['POST'])
def create_post():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    content = request.form['content']
    if content.strip():
        conn = get_db()
        conn.execute('INSERT INTO posts (content, user_id) VALUES (?, ?)', (content, session['user_id']))
        conn.commit()
        conn.close()
    return redirect(url_for('index'))

@app.route('/like/<int:post_id>')
def like(post_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db()
    existing = conn.execute('SELECT 1 FROM likes WHERE user_id = ? AND post_id = ?', 
                           (session['user_id'], post_id)).fetchone()
    
    if existing:
        conn.execute('DELETE FROM likes WHERE user_id = ? AND post_id = ?', (session['user_id'], post_id))
        conn.execute('UPDATE posts SET likes = likes - 1 WHERE id = ?', (post_id,))
    else:
        conn.execute('INSERT INTO likes (user_id, post_id) VALUES (?, ?)', (session['user_id'], post_id))
        conn.execute('UPDATE posts SET likes = likes + 1 WHERE id = ?', (post_id,))
    
    conn.commit()
    conn.close()
    return redirect(request.referrer or url_for('index'))

@app.route('/delete_post/<int:post_id>')
def delete_post(post_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db()
    post = conn.execute('SELECT user_id FROM posts WHERE id = ?', (post_id,)).fetchone()
    if post and post['user_id'] == session['user_id']:
        conn.execute('DELETE FROM likes WHERE post_id = ?', (post_id,))
        conn.execute('DELETE FROM posts WHERE id = ?', (post_id,))
        conn.commit()
    
    conn.close()
    return redirect(url_for('profile'))

@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    posts = conn.execute('SELECT * FROM posts WHERE user_id = ? ORDER BY created_at DESC', (session['user_id'],)).fetchall()
    
    posts_list = []
    for post in posts:
        post_dict = {
            'id': post['id'],
            'content': post['content'],
            'likes': post['likes'],
            'created_at': post['created_at'],
            'created_ago': time_ago(post['created_at'])
        }
        posts_list.append(post_dict)
    
    conn.close()
    return render_template('profile.html', user=user, posts=posts_list)

@app.route('/user/<username>')
def user_profile(username):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    
    if not user:
        abort(404)
    
    posts = conn.execute('SELECT * FROM posts WHERE user_id = ? ORDER BY created_at DESC', (user['id'],)).fetchall()
    
    posts_list = []
    for post in posts:
        # Проверяем, лайкнул ли текущий пользователь этот пост
        liked = conn.execute('SELECT 1 FROM likes WHERE user_id = ? AND post_id = ?', 
                            (session['user_id'], post['id'])).fetchone() is not None
        
        post_dict = {
            'id': post['id'],
            'content': post['content'],
            'likes': post['likes'],
            'created_at': post['created_at'],
            'created_ago': time_ago(post['created_at']),
            'liked': liked
        }
        posts_list.append(post_dict)
    
    conn.close()
    return render_template('user_profile.html', profile_user=user, posts=posts_list)

@app.route('/update_avatar', methods=['POST'])
def update_avatar():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if 'avatar' not in request.files:
        return redirect(url_for('profile'))
    
    file = request.files['avatar']
    if file.filename == '':
        return redirect(url_for('profile'))
    
    if file:
        ext = file.filename.rsplit('.', 1)[-1].lower()
        filename = secure_filename(f"{session['user_id']}_{datetime.now().timestamp()}.{ext}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        conn = get_db()
        conn.execute('UPDATE users SET avatar = ? WHERE id = ?', (f'/static/avatars/{filename}', session['user_id']))
        conn.commit()
        conn.close()
    
    return redirect(url_for('profile'))

@app.route('/update_bio', methods=['POST'])
def update_bio():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    bio = request.form['bio']
    conn = get_db()
    conn.execute('UPDATE users SET bio = ? WHERE id = ?', (bio, session['user_id']))
    conn.commit()
    conn.close()
    
    return redirect(url_for('profile'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)