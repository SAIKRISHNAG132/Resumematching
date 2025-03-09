from fastapi import FastAPI, HTTPException 
import pymongo
import google.generativeai as genai
import os
import logging
from bson import ObjectId  # Import ObjectId

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Initialize FastAPI app
app = FastAPI()
@app.get("/")
def home():
    return {"message": "Welcome to the Job Matching API!"}

# Load API Key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("Missing GEMINI_API_KEY environment variable!")

# MongoDB Connection
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://testing_udbhavx:UdbhavX@udbhavx.2kzuc.mongodb.net/")
client = pymongo.MongoClient(MONGO_URI)
db = client["test"]  # Changed database name
resumes_collection = db["resume"]  # Changed collection name
jobs_collection = db["job_description"]  # Changed collection name

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
    Provide ONLY a numerical match percentage (0-100) without any extra text.
    """
    try:
        response = model.generate_content(prompt)
        match_percentage = float(response.text.strip())
        return max(0, min(100, match_percentage))
    except Exception as e:
        logging.error(f"Error with Gemini API: {e}")
        raise HTTPException(status_code=500, detail=f"Error with Gemini API: {e}")


@app.post("/update_match_scores")
def update_match_scores():
    """Fetch resumes & jobs, use Gemini API for matching, and update MongoDB (job_description collection)."""
    resumes = list(db["resume"].find())  # Changed collection reference
    jobs = list(db["job_description"].find())  # Changed collection reference

    updated_jobs = []

    for job in jobs:
        job_id = job["_id"]
        job_text = job.get("text")
        if not job_text:
            continue  # Skip if no job description text

        job["match_percentages"] = {}  # Initialize dictionary to store match percentages

        for resume in resumes:
            resume_id = resume["_id"]
            resume_text = resume.get("text")
            if not resume_text:
                continue  # Skip if no resume text

            match_percentage = get_match_percentage(resume_text, job_text)
            job["match_percentages"][str(resume_id)] = match_percentage

            logging.info(f"Match percentage: {match_percentage} for job: {job_id}, resume: {resume_id}")

        db["job_description"].update_one(  # Changed collection reference
            {"_id": job_id},
            {"$set": {"match_percentages": job["match_percentages"]}},
        )

        updated_jobs.append(
            {"job_id": str(job_id), "match_percentages": job["match_percentages"]}
        )  # Convert job_id to string.

    return {"message": "Matching process completed!", "updated_jobs": updated_jobs}
