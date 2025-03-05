from fastapi import FastAPI, HTTPException
import pymongo
import google.generativeai as genai
import os
# Initialize FastAPI app
app = FastAPI()
# Load API Key
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    raise RuntimeError("Missing GEMINI_API_KEY environment variable!")
# MongoDB Connection (Use environment variables for security)
#MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://Adithyasharmak:Akshara7@cluster0.8fqgo.mongodb.net/")
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://krishnasai:krishna132@cluster0.wjww1.mongodb.net/")
#MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://testing_udbhavx:UdbhavX@12@udbhavx.2kzuc.mongodb.net/")
client = pymongo.MongoClient(MONGO_URI)
db = client["job_matching"]
resumes_collection = db["resumes"]
jobs_collection = db["jobs"]
matches_collection = db["matches"]  # Store match scores
# Initialize Gemini API
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")
def get_match_percentage(resume_text, job_text):
    """Use Gemini API to compare resume and job description and return a match percentage."""
    prompt = f"""
    You are an expert in resume-job matching. Given the following job description and resume, 
    determine how well they match on a scale of 0 to 100, considering experience, skills, and job relevance.
    Resume:
    ----------------
    {resume_text}
    Job Description:
    ----------------
    {job_text}
    Provide ONLY a single numerical match percentage (0-100) without any extra text.
    """
    try:
        response = model.generate_content(prompt)
        match_percentage = float(response.text.strip())  # Extract numerical value
        return max(0, min(100, match_percentage))  # Ensure it's within 0-100 range
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error with Gemini API: {e}")
@app.post("/update_match_scores")
def update_match_scores():
    """Fetch resumes & jobs, use Gemini API for matching, and update MongoDB."""
    resumes = list(resumes_collection.find())  # Get all resumes
    jobs = list(jobs_collection.find())  # Get all jobs
    updated_matches = []
    for resume in resumes:
        resume_id = resume["_id"]
        resume_text = resume.get("text")
        if not resume_text:
            continue  # Skip if no resume text
        for job in jobs:
            job_id = job["_id"]
            job_text = job.get("text")
            if not job_text:
                continue  # Skip if no job description text
            # Check if match percentage already exists
            match_record = matches_collection.find_one({"resume_id": resume_id, "job_id": job_id})
            if match_record and match_record.get("match_percentage") not in [None, 0]:
                continue  # Skip if match percentage already exists
            # Get match percentage from Gemini API
            match_percentage = get_match_percentage(resume_text, job_text)
            if match_percentage is not None:
                # Update or insert match score in 'matches' collection
                matches_collection.update_one(
                    {"resume_id": resume_id, "job_id": job_id},
                    {"$set": {"match_percentage": match_percentage}},
                    upsert=True
                )
                updated_matches.append({"resume_id": resume_id, "job_id": job_id, "match_percentage": match_percentage})
    return {"message": "Matching process completed!", "updated_matches": updated_matches}


