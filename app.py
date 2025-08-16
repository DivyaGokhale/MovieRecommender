from flask import Flask, render_template,session,make_response
import pickle
import requests
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

from models import db, User
from fuzzywuzzy import process

from functools import wraps
from flask import make_response

def nocache(view):
    @wraps(view)
    def no_cache_view(*args, **kwargs):
        response = make_response(view(*args, **kwargs))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    return no_cache_view


def suggest_close_titles(user_input, limit=5):
    raw_matches = process.extract(user_input, all_movie_titles, limit=limit)
    enhanced = []
    for title, score in raw_matches:
        poster = fetch_poster(title) or "https://via.placeholder.com/150"
        enhanced.append((title, poster, score))
    return enhanced


app = Flask(__name__)
app.secret_key = 'super-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

from flask import request, redirect

@login_manager.unauthorized_handler
def handle_unauthorized():
    return redirect('/login?next=' + request.path)


with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# Load preprocessed data
movies = pickle.load(open('artifacts/movie_list.pkl', 'rb'))
similarity = pickle.load(open('artifacts/similarity.pkl', 'rb'))
all_genres = pickle.load(open('artifacts/genres.pkl', 'rb'))

all_movie_titles = movies['title'].tolist()

def recommend(movie):
    if movie not in movies['title'].values:
        return []

    index = movies[movies['title'] == movie].index[0]
    distances = list(enumerate(similarity[index]))
    sorted_distances = sorted(distances, reverse=True, key=lambda x: x[1])
    recommendations = []
    for i in sorted_distances[1:31]:
        title = movies.iloc[i[0]].title
        poster = fetch_poster(title)
        recommendations.append((title, poster))
    return recommendations

poster_cache = {}

def fetch_poster(movie_title):
    if movie_title in poster_cache:
        return poster_cache[movie_title]

    api_key = "5891e172326946cfa626f1f0cde97c6e"
    url = f"https://api.themoviedb.org/3/search/movie?api_key={api_key}&query={movie_title}"
    try:
        response = requests.get(url)
        data = response.json()
        if data["results"]:
            poster_path = data["results"][0]["poster_path"]
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
            poster_cache[movie_title] = poster_url
            return poster_url
    except:
        pass
    return "https://via.placeholder.com/150"

def get_movies_by_letter(letter):
    letter = letter.lower()
    return [title for title in all_movie_titles if title.lower().startswith(letter)]


@app.route('/')
def home():
    return render_template("home_page.html")


from models import SearchHistory  # already in use

@app.route('/recommend', methods=['POST', 'GET'])
@login_required
@nocache
def recommend_movie():
    if request.method == 'POST':
        movie_name = request.form['movie_name']
    else:
        movie_name = request.args.get('movie_name')

    # 🔐 Save search to SearchHistory
    if current_user.is_authenticated and movie_name:
        history = SearchHistory(user_id=current_user.id, search_term=movie_name)
        db.session.add(history)
        db.session.commit()

    page = int(request.args.get('page', 1))
    per_page = 12
    recommendations = recommend(movie_name)
    not_found = (len(recommendations) == 0)
    suggestions = []

    
    if not_found:
        suggestions = suggest_close_titles(movie_name)

    total = len(recommendations)
    start = (page - 1) * per_page
    end = start + per_page
    recommendations_paginated = recommendations[start:end]



    return render_template(
        'recommend.html',
        movie_name=movie_name,
        recommendations=recommendations_paginated,
        not_found=not_found,
        suggestions=suggestions,
        current_page=page,
        total_pages=(total + per_page - 1) // per_page
    )

@app.route('/movies_by_letter_ajax', methods=['POST'])
@login_required
@nocache
def movies_by_letter_ajax():
    letter = request.form['letter']
    matching_movies = get_movies_by_letter(letter)
    return render_template('movie_suggestions.html', movies=matching_movies)

@app.route('/search_by_genre')
@login_required
@nocache
def search_by_genre():
    genre = request.args.get('genre')
    page = int(request.args.get('page', 1))
    per_page = 12

    import pandas as pd
    df_raw = pd.read_csv('tmdb_5000_movies.csv')
    df_credits = pd.read_csv('tmdb_5000_credits.csv')
    df = df_raw.merge(df_credits, on='title')
    df['genres'] = df['genres'].apply(lambda x: [i['name'].replace(" ", "") for i in eval(x)])
    matches = df[df['genres'].apply(lambda g: genre.lower() in [x.lower() for x in g])]

    total = matches.shape[0]
    start = (page - 1) * per_page
    end = start + per_page

    movies_paginated = matches.iloc[start:end]
    genre_results = [(row['title'], fetch_poster(row['title'])) for _, row in movies_paginated.iterrows()]

    return render_template(
        'recommend.html',
        movie_name=genre.capitalize(), 
        recommendations=genre_results,
        not_found=(len(genre_results) == 0),
        suggestions=[],
        current_page=page,
        total_pages=(total + per_page - 1) // per_page
    )

emotion_genre_map = {
    "happy": ["Comedy", "Adventure"],
    "sad": ["Drama", "Romance"],
    "excited": ["Action", "Thriller"],
    "relaxed": ["Animation", "Fantasy"]
}

@app.route('/recommend_by_emotion', methods=['POST', 'GET'])
@login_required
@nocache
def recommend_by_emotion():
    if request.method == 'POST':
        emotion = request.form['emotion']
    else:
        emotion = request.args.get('emotion')

    genres = emotion_genre_map.get(emotion.lower(), [])
    import pandas as pd
    df_raw = pd.read_csv('tmdb_5000_movies.csv')
    df_credits = pd.read_csv('tmdb_5000_credits.csv')
    df = df_raw.merge(df_credits, on='title')
    df['genres'] = df['genres'].apply(lambda x: [i['name'].replace(" ", "") for i in eval(x)])

    matches = df[df['genres'].apply(lambda g: any(em.lower() in [x.lower() for x in g] for em in genres))]

    page = int(request.args.get('page', 1))
    per_page = 12
    total = matches.shape[0]
    start = (page - 1) * per_page
    end = start + per_page

    movies_paginated = matches.iloc[start:end]
    recommendations = [(row['title'], fetch_poster(row['title'])) for _, row in movies_paginated.iterrows()]

    return render_template(
        'recommend.html',
        movie_name=emotion.capitalize(),
        recommendations=recommendations,
        not_found=(len(recommendations) == 0),
        suggestions=[],
        current_page=page,
        total_pages=(total + per_page - 1) // per_page
    )

def get_recommendations_from_searches(terms):
    recommended = set()
    results = []

    for movie in terms:
        if movie in movies['title'].values:
            index = movies[movies['title'] == movie].index[0]
            distances = list(enumerate(similarity[index]))
            sorted_distances = sorted(distances[1:10], key=lambda x: x[1], reverse=True)

            for i in sorted_distances:
                title = movies.iloc[i[0]].title
                if title not in recommended:
                    poster = fetch_poster(title)
                    results.append((title, poster))
                    recommended.add(title)

    return results

@app.route('/search_by_age')
@login_required
@nocache
def search_by_age():
    age_group = request.args.get('age_group')
    page = int(request.args.get('page', 1))
    per_page = 12

    import pandas as pd
    df_raw = pd.read_csv('tmdb_5000_movies.csv')
    df_credits = pd.read_csv('tmdb_5000_credits.csv')
    df = df_raw.merge(df_credits, on='title')
    df['genres'] = df['genres'].apply(lambda x: [i['name'].replace(" ", "") for i in eval(x)])

    group_map = {
        "kids": ["Animation", "Family"],
        "teens": ["Adventure", "Fantasy", "Comedy"],
        "adults": ["Thriller", "Crime", "Horror"],
        "all": ["Drama", "Romance", "Music", "Mystery"]
    }

    selected_genres = group_map.get(age_group.lower(), [])
    matches = df[df['genres'].apply(lambda g: any(genre.lower() in [x.lower() for x in g] for genre in selected_genres))]

    total = matches.shape[0]
    start = (page - 1) * per_page
    end = start + per_page
    movies_paginated = matches.iloc[start:end]

    age_results = [(row['title'], fetch_poster(row['title'])) for _, row in movies_paginated.iterrows()]

    return render_template(
        'recommend.html',
        movie_name=age_group.capitalize(),  
        recommendations=age_results,
        not_found=(len(age_results) == 0),
        suggestions=[],
        current_page=page,
        total_pages=(total + per_page - 1) // per_page
    )


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')

        if User.query.filter_by(username=username).first():
            return "Username already exists!"

        new_user = User(username=username, password=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        return redirect('/dashboard')
    return render_template('register.html')


@app.route('/home_page', methods=['GET', 'POST'])
def home_page():
    return render_template('home_page.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect('/dashboard') 
        return "Invalid credentials"
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect('/login')


@app.route('/profile')
@login_required
@nocache
def profile():
    recent_searches = SearchHistory.query.filter_by(user_id=current_user.id)\
                        .order_by(SearchHistory.timestamp.desc()).limit(10).all()

    #based on search keywords
    search_terms = [s.search_term for s in recent_searches]
    suggestions = get_recommendations_from_searches(search_terms)

    return render_template('profile.html',
                           user=current_user,
                           searches=recent_searches,
                           suggestions=suggestions)

@app.route('/dashboard')
@login_required
@nocache
def dashboard():
    recent_searches = SearchHistory.query.filter_by(user_id=current_user.id)\
        .order_by(SearchHistory.timestamp.desc()).all()

    seen_terms = set()
    search_with_posters = []
    for s in recent_searches:
        if s.search_term not in seen_terms:
            search_with_posters.append({
                'search_term': s.search_term,
                'poster': fetch_poster(s.search_term)
            })
            seen_terms.add(s.search_term)

    #suggestions based on search terms
    suggestions = get_recommendations_from_searches(list(seen_terms))


    return render_template("index.html",
                           user=current_user,
                           all_genres=all_genres,
                           searches=search_with_posters,
                           suggestions=suggestions)

        
@app.route('/trending')
@login_required
@nocache
def trending():
    url = f"https://api.themoviedb.org/3/trending/movie/week?api_key=5891e172326946cfa626f1f0cde97c6e"
    response = requests.get(url)
    data = response.json()
    results = [(movie['title'], f"https://image.tmdb.org/t/p/w500{movie['poster_path']}") 
               for movie in data.get('results', []) if movie.get('poster_path')]
    return render_template("recommend.html", movie_name="Trending Now", recommendations=results, not_found=False, suggestions=[])


@app.route('/top_rated')
@login_required
@nocache
def top_rated():
    url = f"https://api.themoviedb.org/3/movie/top_rated?api_key=5891e172326946cfa626f1f0cde97c6e"
    response = requests.get(url)
    data = response.json()
    results = [(movie['title'], f"https://image.tmdb.org/t/p/w500{movie['poster_path']}") 
               for movie in data.get('results', []) if movie.get('poster_path')]
    return render_template("recommend.html", movie_name="Top Rated", recommendations=results, not_found=False, suggestions=[])

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        user = User.query.filter_by(email=email).first()
        if user:
            token = serializer.dumps(email, salt='password-reset-salt')
            reset_url = url_for('reset_password', token=token, _external=True)
            print(f"🔗 Password reset link: {reset_url}")  # For testing
            flash('Password reset link has been sent! (Check terminal for now)', 'info')
        else:
            flash('Email not found', 'danger')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')
    

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        email = serializer.loads(token, salt='password-reset-salt', max_age=3600)
    except SignatureExpired:
        flash('The reset link has expired.', 'danger')
        return redirect(url_for('forgot_password'))
    except BadSignature:
        flash('Invalid reset link.', 'danger')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        new_password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user:
            user.password = generate_password_hash(new_password)
            db.session.commit()
            flash('Your password has been updated!', 'success')
            return redirect(url_for('login'))
    return render_template('reset_password.html')

if __name__ == '__main__':
    serializer = URLSafeTimedSerializer(app.secret_key)
    app.run(debug=True)
