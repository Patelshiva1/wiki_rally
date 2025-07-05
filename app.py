from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from typing import List, Dict, Optional
import json
import uuid
from datetime import datetime
import sqlite3
import hashlib
import os

app = FastAPI(title="WIKI RALLY", version="2.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import enhanced quiz data
from quiz_data import QUIZ_DATA, STATES_INFO, FESTIVALS_DATA

# Database setup
DATABASE_PATH = "quiz_app.db"

def init_database():
    """Initialize SQLite database with required tables"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_guest BOOLEAN DEFAULT FALSE,
            is_admin BOOLEAN DEFAULT FALSE
        )
    ''')
    
    # Quiz attempts table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS quiz_attempts (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            state TEXT NOT NULL,
            score INTEGER NOT NULL,
            total_questions INTEGER NOT NULL,
            percentage REAL NOT NULL,
            answers TEXT NOT NULL,
            completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # User stats table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id TEXT PRIMARY KEY,
            total_quizzes INTEGER DEFAULT 0,
            total_score REAL DEFAULT 0,
            best_score REAL DEFAULT 0,
            states_attempted TEXT DEFAULT '[]',
            favorite_states TEXT DEFAULT '[]',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # User interactions table (for discover/explore features)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_interactions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            interaction_type TEXT NOT NULL,
            state_name TEXT,
            place_name TEXT,
            interaction_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # State visits tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS state_visits (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            state_name TEXT NOT NULL,
            visit_type TEXT NOT NULL,
            visit_count INTEGER DEFAULT 1,
            last_visit TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Enhanced leaderboard view
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS enhanced_leaderboard AS
        SELECT 
            u.username,
            us.total_quizzes,
            ROUND(us.total_score / NULLIF(us.total_quizzes, 0), 2) as avg_score,
            us.best_score,
            COUNT(DISTINCT qa.state) as states_completed,
            COUNT(DISTINCT sv.state_name) as states_explored,
            u.created_at
        FROM users u
        LEFT JOIN user_stats us ON u.id = us.user_id
        LEFT JOIN quiz_attempts qa ON u.id = qa.user_id
        LEFT JOIN state_visits sv ON u.id = sv.user_id
        WHERE u.is_guest = FALSE
        GROUP BY u.id, u.username, us.total_quizzes, us.best_score
        ORDER BY us.best_score DESC, us.total_quizzes DESC, states_completed DESC
    ''')
    
    conn.commit()
    conn.close()

# Initialize database on startup
init_database()

# Enhanced Pydantic models
class UserRegistration(BaseModel):
    username: str
    email: EmailStr
    password: Optional[str] = None
    is_guest: bool = False

class UserLogin(BaseModel):
    username: str
    password: Optional[str] = None

class QuizSubmission(BaseModel):
    user_id: str
    state: str
    answers: List[str]

class UserInteraction(BaseModel):
    user_id: str
    interaction_type: str  # 'discover_view', 'explore_place', 'favorite_state'
    state_name: Optional[str] = None
    place_name: Optional[str] = None
    interaction_data: Optional[Dict] = None

class StateVisit(BaseModel):
    user_id: str
    state_name: str
    visit_type: str  # 'quiz', 'discover', 'explore'

# Helper functions
def hash_password(password: str) -> str:
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def generate_id() -> str:
    """Generate unique ID"""
    return str(uuid.uuid4())

# API Routes

@app.get("/", response_class=FileResponse)
async def serve_frontend():
    return FileResponse("index.html")

@app.get("/api/info")
async def api_info():
    return {
        "message": "Indian States Quiz & Explorer API",
        "version": "2.0.0",
        "features": ["Quiz", "Discover", "Explore", "User Stats", "Leaderboard"],
        "endpoints": {
            "auth": ["POST /api/auth/register", "POST /api/auth/login"],
            "quiz": ["GET /api/states", "GET /api/quiz/{state}", "POST /api/quiz/submit"],
            "discover": ["GET /api/discover/states", "GET /api/discover/state/{state}"],
            "explore": ["GET /api/explore/places", "GET /api/explore/state/{state}"],
            "user": ["GET /api/user/{user_id}/stats", "GET /api/user/{user_id}/history"],
            "interactions": ["POST /api/user/interaction", "POST /api/user/visit"],
            "leaderboard": ["GET /api/leaderboard"]
        }
    }

# Enhanced states endpoint - THIS IS THE KEY FIX
@app.get("/api/states")
async def get_states():
    """Get list of all available states with enhanced information"""
    states_list = []
    
    # Ensure we get ALL states from QUIZ_DATA
    all_state_names = sorted(list(QUIZ_DATA.keys()))
    
    for state_name in all_state_names:
        state_info = STATES_INFO.get(state_name, {})
        states_list.append({
            "name": state_name,
            "capital": state_info.get("capital", ""),
            "region": state_info.get("region", ""),
            "formation": state_info.get("formation", ""),
            "area": state_info.get("area", ""),
            "population": state_info.get("population", ""),
            "quiz_questions": len(QUIZ_DATA[state_name])
        })
    
    return {
        "states": states_list,
        "total_states": len(states_list),
        "all_state_names": all_state_names,  # Added for debugging
        "regions": {
            "north": len([s for s in states_list if s.get("region") == "north"]),
            "south": len([s for s in states_list if s.get("region") == "south"]),
            "east": len([s for s in states_list if s.get("region") == "east"]),
            "west": len([s for s in states_list if s.get("region") == "west"]),
            "northeast": len([s for s in states_list if s.get("region") == "northeast"])
        }
    }

# Discover endpoints
@app.get("/api/discover/states")
async def get_discover_states():
    """Get comprehensive state information for discover page"""
    discover_data = []
    
    for state_name, info in STATES_INFO.items():
        festivals = FESTIVALS_DATA.get(state_name, [])
        discover_data.append({
            "name": state_name,
            "capital": info.get("capital"),
            "formation": info.get("formation"),
            "area": info.get("area"),
            "population": info.get("population"),
            "languages": info.get("languages", []),
            "description": info.get("description"),
            "famousFor": info.get("famousFor", []),
            "region": info.get("region"),
            "festivals": festivals[:3],  # Top 3 festivals
            "wikipedia": info.get("wikipedia")
        })
    
    return {
        "states": discover_data,
        "total_states": len(discover_data)
    }

@app.get("/api/discover/state/{state_name}")
async def get_state_details(state_name: str):
    """Get detailed information about a specific state"""
    if state_name not in STATES_INFO:
        raise HTTPException(status_code=404, detail=f"State '{state_name}' not found")
    
    state_info = STATES_INFO[state_name]
    festivals = FESTIVALS_DATA.get(state_name, [])
    
    return {
        "name": state_name,
        "info": state_info,
        "festivals": festivals,
        "quiz_available": state_name in QUIZ_DATA,
        "quiz_questions": len(QUIZ_DATA.get(state_name, []))
    }

# Explore endpoints
@app.get("/api/explore/places")
async def get_explore_places():
    """Get places to explore across all states"""
    all_places = []
    
    for state_name, info in STATES_INFO.items():
        places = info.get("places", [])
        for place in places:
            all_places.append({
                "name": place.get("name"),
                "type": place.get("type"),
                "description": place.get("description"),
                "state": state_name,
                "region": info.get("region"),
                "wikipedia": info.get("wikipedia")
            })
    
    # Categorize places
    categories = {}
    for place in all_places:
        place_type = place["type"]
        if place_type not in categories:
            categories[place_type] = []
        categories[place_type].append(place)
    
    return {
        "places": all_places,
        "total_places": len(all_places),
        "categories": categories,
        "total_categories": len(categories)
    }

@app.get("/api/explore/state/{state_name}")
async def get_state_places(state_name: str):
    """Get places to explore in a specific state"""
    if state_name not in STATES_INFO:
        raise HTTPException(status_code=404, detail=f"State '{state_name}' not found")
    
    state_info = STATES_INFO[state_name]
    places = state_info.get("places", [])
    
    return {
        "state": state_name,
        "places": places,
        "total_places": len(places),
        "state_info": {
            "capital": state_info.get("capital"),
            "region": state_info.get("region"),
            "description": state_info.get("description"),
            "wikipedia": state_info.get("wikipedia")
        }
    }

# Enhanced user interaction tracking
@app.post("/api/user/interaction")
async def log_user_interaction(interaction: UserInteraction):
    """Log user interactions for analytics and personalization"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        interaction_id = generate_id()
        cursor.execute('''
            INSERT INTO user_interactions (id, user_id, interaction_type, state_name, place_name, interaction_data, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            interaction_id,
            interaction.user_id,
            interaction.interaction_type,
            interaction.state_name,
            interaction.place_name,
            json.dumps(interaction.interaction_data) if interaction.interaction_data else None,
            datetime.now()
        ))
        
        conn.commit()
        return {"message": "Interaction logged successfully", "interaction_id": interaction_id}
    
    finally:
        conn.close()

@app.post("/api/user/visit")
async def log_state_visit(visit: StateVisit):
    """Log state visits for analytics"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Check if visit exists
        cursor.execute('''
            SELECT id, visit_count FROM state_visits 
            WHERE user_id = ? AND state_name = ? AND visit_type = ?
        ''', (visit.user_id, visit.state_name, visit.visit_type))
        
        existing_visit = cursor.fetchone()
        
        if existing_visit:
            # Update existing visit
            cursor.execute('''
                UPDATE state_visits 
                SET visit_count = visit_count + 1, last_visit = ?
                WHERE id = ?
            ''', (datetime.now(), existing_visit['id']))
        else:
            # Create new visit record
            visit_id = generate_id()
            cursor.execute('''
                INSERT INTO state_visits (id, user_id, state_name, visit_type, visit_count, last_visit)
                VALUES (?, ?, ?, ?, 1, ?)
            ''', (visit_id, visit.user_id, visit.state_name, visit.visit_type, datetime.now()))
        
        conn.commit()
        return {"message": "Visit logged successfully"}
    
    finally:
        conn.close()

# Enhanced user stats
@app.get("/api/user/{user_id}/stats")
async def get_enhanced_user_stats(user_id: str):
    """Get enhanced user statistics including discover and explore data"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Basic user stats
        cursor.execute('''
            SELECT u.username, us.total_quizzes, us.total_score, us.best_score, us.states_attempted, us.favorite_states
            FROM users u
            LEFT JOIN user_stats us ON u.id = us.user_id
            WHERE u.id = ?
        ''', (user_id,))
        
        result = cursor.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="User not found")
        
        # State visits
        cursor.execute('''
            SELECT state_name, visit_type, visit_count, last_visit
            FROM state_visits
            WHERE user_id = ?
            ORDER BY last_visit DESC
        ''', (user_id,))
        
        visits = cursor.fetchall()
        
        # User interactions
        cursor.execute('''
            SELECT interaction_type, COUNT(*) as count
            FROM user_interactions
            WHERE user_id = ?
            GROUP BY interaction_type
        ''', (user_id,))
        
        interactions = cursor.fetchall()
        
        avg_score = round(result['total_score'] / result['total_quizzes'], 2) if result['total_quizzes'] > 0 else 0
        states_attempted = json.loads(result['states_attempted']) if result['states_attempted'] else []
        favorite_states = json.loads(result['favorite_states']) if result['favorite_states'] else []
        
        return {
            "user_id": user_id,
            "username": result['username'],
            "quiz_stats": {
                "total_quizzes": result['total_quizzes'] or 0,
                "avg_score": avg_score,
                "best_score": result['best_score'] or 0,
                "states_attempted": states_attempted,
                "states_completed": len(states_attempted)
            },
            "exploration_stats": {
                "states_visited": len(set([visit['state_name'] for visit in visits])),
                "total_visits": sum([visit['visit_count'] for visit in visits]),
                "favorite_states": favorite_states,
                "recent_visits": [
                    {
                        "state": visit['state_name'],
                        "type": visit['visit_type'],
                        "count": visit['visit_count'],
                        "last_visit": visit['last_visit']
                    } for visit in visits[:10]
                ]
            },
            "interaction_summary": {
                interaction['interaction_type']: interaction['count'] 
                for interaction in interactions
            }
        }
    
    finally:
        conn.close()

# Enhanced leaderboard
@app.get("/api/leaderboard")
async def get_enhanced_leaderboard(limit: int = 50):
    """Get enhanced leaderboard with exploration data"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT username, total_quizzes, avg_score, best_score, states_completed, states_explored, created_at
            FROM enhanced_leaderboard
            LIMIT ?
        ''', (limit,))
        
        leaderboard = cursor.fetchall()
        
        return {
            "leaderboard": [
                {
                    "rank": i + 1,
                    "username": entry['username'],
                    "quiz_score": entry['best_score'] or 0,
                    "total_quizzes": entry['total_quizzes'] or 0,
                    "avg_score": entry['avg_score'] or 0,
                    "states_completed": entry['states_completed'] or 0,
                    "states_explored": entry['states_explored'] or 0,
                    "member_since": entry['created_at']
                }
                for i, entry in enumerate(leaderboard)
            ],
            "total_users": len(leaderboard)
        }
    
    finally:
        conn.close()

# Global analytics endpoint
@app.get("/api/analytics/global")
async def get_global_analytics():
    """Get global application analytics"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Basic stats
        cursor.execute("SELECT COUNT(*) as total_users FROM users WHERE is_guest = FALSE")
        total_users = cursor.fetchone()['total_users']
        
        cursor.execute("SELECT COUNT(*) as total_guests FROM users WHERE is_guest = TRUE")
        total_guests = cursor.fetchone()['total_guests']
        
        cursor.execute("SELECT COUNT(*) as total_attempts FROM quiz_attempts")
        total_attempts = cursor.fetchone()['total_attempts']
        
        # Most popular states
        cursor.execute('''
            SELECT state, COUNT(*) as attempts 
            FROM quiz_attempts 
            GROUP BY state 
            ORDER BY attempts DESC 
            LIMIT 5
        ''')
        popular_quiz_states = cursor.fetchall()
        
        cursor.execute('''
            SELECT state_name, SUM(visit_count) as total_visits
            FROM state_visits 
            WHERE visit_type = 'discover'
            GROUP BY state_name 
            ORDER BY total_visits DESC 
            LIMIT 5
        ''')
        popular_discover_states = cursor.fetchall()
        
        cursor.execute('''
            SELECT state_name, SUM(visit_count) as total_visits
            FROM state_visits 
            WHERE visit_type = 'explore'
            GROUP BY state_name 
            ORDER BY total_visits DESC 
            LIMIT 5
        ''')
        popular_explore_states = cursor.fetchall()
        
        # Average performance
        cursor.execute("SELECT AVG(percentage) as avg_score FROM quiz_attempts")
        global_avg_score = cursor.fetchone()['avg_score'] or 0
        
        return {
            "user_stats": {
                "total_users": total_users,
                "total_guests": total_guests,
                "total_quiz_attempts": total_attempts
            },
            "content_stats": {
                "total_states": len(QUIZ_DATA),
                "total_quiz_questions": sum(len(questions) for questions in QUIZ_DATA.values()),
                "total_festivals": sum(len(festivals) for festivals in FESTIVALS_DATA.values()),
                "total_places": sum(len(info.get("places", [])) for info in STATES_INFO.values())
            },
            "popularity": {
                "top_quiz_states": [
                    {"state": state['state'], "attempts": state['attempts']} 
                    for state in popular_quiz_states
                ],
                "top_discover_states": [
                    {"state": state['state_name'], "visits": state['total_visits']} 
                    for state in popular_discover_states
                ],
                "top_explore_states": [
                    {"state": state['state_name'], "visits": state['total_visits']} 
                    for state in popular_explore_states
                ]
            },
            "performance": {
                "global_avg_score": round(global_avg_score, 2)
            }
        }
    
    finally:
        conn.close()

# Existing endpoints (enhanced)
@app.get("/api/quiz/{state}")
async def get_quiz(state: str):
    """Get quiz questions for a specific state"""
    if state not in QUIZ_DATA:
        raise HTTPException(status_code=404, detail=f"State '{state}' not found")
    
    questions = []
    for q in QUIZ_DATA[state]:
        questions.append({
            "question": q["question"],
            "options": q["options"]
        })
    
    state_info = STATES_INFO.get(state, {})
    
    return {
        "state": state,
        "questions": questions,
        "total_questions": len(questions),
        "state_info": {
            "capital": state_info.get("capital"),
            "region": state_info.get("region"),
            "description": state_info.get("description")
        }
    }

@app.post("/api/auth/register")
async def register_user(user_data: UserRegistration):
    """Register a new user or guest"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        user_id = generate_id()
        password_hash = hash_password(user_data.password) if user_data.password else None
        
        if not user_data.is_guest:
            cursor.execute(
                "SELECT id FROM users WHERE username = ? OR email = ?",
                (user_data.username, user_data.email)
            )
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail="Username or email already exists")
        
        cursor.execute('''
            INSERT INTO users (id, username, email, password_hash, is_guest, last_login)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, user_data.username, user_data.email, password_hash, user_data.is_guest, datetime.now()))
        
        cursor.execute('INSERT INTO user_stats (user_id) VALUES (?)', (user_id,))
        
        conn.commit()
        
        return {
            "user_id": user_id,
            "username": user_data.username,
            "email": user_data.email,
            "is_guest": user_data.is_guest,
            "message": "User registered successfully"
        }
    
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Username or email already exists")
    finally:
        conn.close()

@app.post("/api/auth/login")
async def login_user(login_data: UserLogin):
    """Login user"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "SELECT id, username, email, password_hash, is_guest FROM users WHERE username = ? OR email = ?",
            (login_data.username, login_data.username)
        )
        user = cursor.fetchone()

        if not user:
            raise HTTPException(status_code=401, detail="Invalid username or password")
        
        if not user['is_guest'] and login_data.password:
            if hash_password(login_data.password) != user['password_hash']:
                raise HTTPException(status_code=401, detail="Invalid username or password")
        
        cursor.execute(
            "UPDATE users SET last_login = ? WHERE id = ?",
            (datetime.now(), user['id'])
        )
        conn.commit()
        
        return {
            "user_id": user['id'],
            "username": user['username'],
            "email": user['email'],
            "is_guest": user['is_guest'],
            "message": "Login successful"
        }
    
    finally:
        conn.close()


@app.post("/api/quiz/submit")
async def submit_quiz(submission: QuizSubmission):
    """Submit quiz answers and get results"""
    if submission.state not in QUIZ_DATA:
        raise HTTPException(status_code=404, detail=f"State '{submission.state}' not found")
    
    questions = QUIZ_DATA[submission.state]
    
    if len(submission.answers) != len(questions):
        raise HTTPException(status_code=400, detail="Number of answers doesn't match number of questions")
    
    score = 0
    results = []
    
    for i, answer in enumerate(submission.answers):
        question = questions[i]
        is_correct = answer == question["correct"]
        if is_correct:
            score += 1
        
        results.append({
            "question": question["question"],
            "user_answer": answer,
            "correct_answer": question["correct"],
            "is_correct": is_correct
        })
    
    percentage = round((score / len(questions)) * 100, 2)
    attempt_id = generate_id()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Insert quiz attempt
        cursor.execute('''
            INSERT INTO quiz_attempts (id, user_id, state, score, total_questions, percentage, answers)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (attempt_id, submission.user_id, submission.state, score, len(questions), percentage, json.dumps(results)))
        
        # Update user stats
        cursor.execute('''
            SELECT total_quizzes, total_score, best_score, states_attempted FROM user_stats WHERE user_id = ?
        ''', (submission.user_id,))
        
        stats = cursor.fetchone()
        if stats:
            new_total_quizzes = stats['total_quizzes'] + 1
            new_total_score = stats['total_score'] + percentage
            new_best_score = max(stats['best_score'], percentage)
            
            states_attempted = json.loads(stats['states_attempted']) if stats['states_attempted'] else []
            if submission.state not in states_attempted:
                states_attempted.append(submission.state)
            
            cursor.execute('''
                UPDATE user_stats 
                SET total_quizzes = ?, total_score = ?, best_score = ?, states_attempted = ?, updated_at = ?
                WHERE user_id = ?
            ''', (new_total_quizzes, new_total_score, new_best_score, json.dumps(states_attempted), datetime.now(), submission.user_id))
        
        # Log state visit
        cursor.execute('''
            INSERT OR REPLACE INTO state_visits (id, user_id, state_name, visit_type, visit_count, last_visit)
            VALUES (?, ?, ?, 'quiz', 
                COALESCE((SELECT visit_count FROM state_visits WHERE user_id = ? AND state_name = ? AND visit_type = 'quiz'), 0) + 1,
                ?)
        ''', (generate_id(), submission.user_id, submission.state, submission.user_id, submission.state, datetime.now()))
        
        conn.commit()
        
        return {
            "attempt_id": attempt_id,
            "score": score,
            "total": len(questions),
            "percentage": percentage,
            "results": results,
            "message": "Quiz submitted successfully"
        }
    
    finally:
        conn.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
