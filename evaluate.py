import pickle
import numpy as np
from sklearn.metrics import precision_score, recall_score, f1_score

# Load vectorized data
movies = pickle.load(open('artifacts/movie_list.pkl', 'rb'))
similarity = pickle.load(open('artifacts/similarity.pkl', 'rb'))

def recommend(title, top_k=10):
    try:
        idx = movies[movies['title'].str.lower() == title.lower()].index[0]
        distances = list(enumerate(similarity[idx]))
        movies_list = sorted(distances, key=lambda x: x[1], reverse=True)[1:top_k+1]
        return [movies.iloc[i[0]]['title'] for i in movies_list]
    except IndexError:
        return []

def evaluate_model(top_k=10, max_samples=100, min_overlap=5):
    precision_scores, recall_scores, f1_scores = [], [], []

    sampled_movies = movies.sample(min(max_samples, len(movies)))

    for _, row in sampled_movies.iterrows():
        title = row['title']
        original_tags = set(row['tags'].split())
        recommended_titles = recommend(title, top_k)

        if not original_tags:
            continue

        y_true = []
        for rec_title in recommended_titles:
            rec_tags = set(movies[movies['title'] == rec_title]['tags'].values[0].split())
            overlap = len(original_tags.intersection(rec_tags))
            y_true.append(1 if overlap >= min_overlap else 0)

        y_pred = [1] * len(recommended_titles)

        if sum(y_true) == 0:
            continue  # skip if no overlap found

        precision_scores.append(precision_score(y_true, y_pred, zero_division=0))
        recall_scores.append(recall_score(y_true, y_pred, zero_division=0))
        f1_scores.append(f1_score(y_true, y_pred, zero_division=0))

    print("\nTag-Based Evaluation")
    print(f"Avg Precision: {np.mean(precision_scores):.2f}")
    print(f"Avg Recall: {np.mean(recall_scores):.2f}")
    print(f"Avg F1-score: {np.mean(f1_scores):.2f}")

if __name__ == "__main__":
    evaluate_model()
