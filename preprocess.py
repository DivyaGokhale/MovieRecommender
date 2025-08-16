# preprocess.py

import pandas as pd
import ast
import pickle
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from nltk.stem.porter import PorterStemmer
import os

def convert(text):
    return [i['name'] for i in ast.literal_eval(text)]

def convert_cast(text):
    return [i['name'] for i in ast.literal_eval(text)[:3]]

def fetch_director(text):
    for i in ast.literal_eval(text):
        if i['job'] == 'Director':
            return [i['name']]
    return []

def remove_space(L):
    return [i.replace(" ", "") for i in L]

def stems(text):
    ps = PorterStemmer()
    return " ".join([ps.stem(word) for word in text.split()])

# Load datasets
movies = pd.read_csv('tmdb_5000_movies.csv')
credits = pd.read_csv('tmdb_5000_credits.csv')

movies = movies.merge(credits, on='title')
movies = movies[['movie_id', 'title', 'overview', 'genres', 'keywords', 'cast', 'crew']]
movies.dropna(inplace=True)

# Process columns
movies['genres'] = movies['genres'].apply(convert).apply(remove_space)
movies['keywords'] = movies['keywords'].apply(convert).apply(remove_space)
movies['cast'] = movies['cast'].apply(convert_cast).apply(remove_space)
movies['crew'] = movies['crew'].apply(fetch_director).apply(remove_space)
movies['overview'] = movies['overview'].apply(lambda x: x.split())

# Create tags
movies['tags'] = movies['overview'] + movies['genres'] + movies['keywords'] + movies['cast'] + movies['crew']
new_df = movies[['movie_id', 'title', 'tags']]
new_df['tags'] = new_df['tags'].apply(lambda x: " ".join(x).lower()).apply(stems)

# Vectorize
cv = TfidfVectorizer(max_features=5000, stop_words='english')
vector = cv.fit_transform(new_df['tags']).toarray()
similarity = cosine_similarity(vector)

# Extract genres
all_genres = sorted({genre for sublist in movies['genres'] for genre in sublist})

# Save everything
if not os.path.exists('artifacts'):
    os.makedirs('artifacts')

pickle.dump(new_df, open('artifacts/movie_list.pkl', 'wb'))
pickle.dump(similarity, open('artifacts/similarity.pkl', 'wb'))
pickle.dump(cv, open('artifacts/vectorizer.pkl', 'wb'))
pickle.dump(all_genres, open('artifacts/genres.pkl', 'wb'))

print("Preprocessing complete.")
