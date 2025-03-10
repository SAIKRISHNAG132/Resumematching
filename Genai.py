import os
import io
import json
import datetime
import fitz  # PyMuPDF for PDF
import docx
import boto3
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from pymongo import MongoClient
from pymongo.server_api import ServerApi
import cohere
from google import genai
from typing import List

# Load environment variables
load_dotenv()

# API Keys from .env file
COHERE_API_KEY = os.getenv('COHERE_API_KEY')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
AWS_ACCESS_KEY = os.getenv('AWS_ACCESS_KEY')
AWS_SECRET_KEY = os.getenv('AWS_SECRET_KEY')
S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME')

# Initialize external services
co = cohere.Client(api_key=COHERE_API_KEY)
gemini_client = genai.Client(api_key=GEMINI_API_KEY)
s3_client = boto3.client('s3', aws_access_key_id=AWS_ACCESS_KEY, aws_secret_access_key=AWS_SECRET_KEY)

# MongoDB connection
MONGO_URI="mongodb+srv://testing_udbhavx:UdbhavX@udbhavx.2kzuc.mongodb.net/"

client = MongoClient(MONGO_URI, server_api=ServerApi('1'))
db = client['test']
resume_collection = db['resume']  

COHERE_EMBEDDING_MODEL = 'embed-english-v3.0'

# FastAPI instance
app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "FastAPI is running!"}

# ------------------ S3 Functions ------------------

def upload_to_s3(file_content: bytes, file_name: str) -> str:
    try:
        s3_client.put_object(Bucket=S3_BUCKET_NAME, Key=file_name, Body=file_content)
        return f"https://{S3_BUCKET_NAME}.s3.amazonaws.com/{file_name}"
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload to S3: {e}")

def get_resume_from_s3(file_name: str) -> bytes:
    try:
        response = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=file_name)
        return response['Body'].read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve file from S3: {e}")

# ------------------ Cohere & Gemini Functions ------------------

def fetch_embeddings(texts: List[str], embedding_type: str = 'search_document') -> List[List[float]]:
    try:
        results = co.embed(
            texts=texts,
            model=COHERE_EMBEDDING_MODEL,
            input_type=embedding_type
        ).embeddings
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cohere embedding fetch failed: {e}")

def synthesize_answer(question: str, context: List[str]) -> str:
    context_str = '\n'.join(context)
    prompt = f"""
    Extract ONLY the total years of experience and list of skills from the following document.
    ---------------------
    {context_str}
    ---------------------
    Provide the answer in the format:
    Years of Experience: <number> \n
    Skills: <comma-separated list>
    """
    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[prompt]
        )
        return response.text
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error communicating with Gemini API: {e}")

# ------------------ API Endpoints ------------------

@app.post("/extract-experience-skills/")
async def extract_experience_skills(file: UploadFile = File(...)):
    try:
        file_extension = file.filename.split('.')[-1].lower()
        file_content = await file.read()

        s3_file_path = f"resume/{file.filename}"

        existing_doc = resume_collection.find_one({"file_name": file.filename})
        if existing_doc:
            file_content = get_resume_from_s3(s3_file_path)
            print(" Using existing resume from S3")
        else:
            s3_url = upload_to_s3(file_content, s3_file_path)
            print("New resume uploaded to S3")

        texts = []
        if file_extension == 'pdf':
            doc = fitz.open(stream=file_content, filetype='pdf')
            texts = [page.get_text() for page in doc]
        elif file_extension == 'docx':
            doc = docx.Document(io.BytesIO(file_content))
            texts = [para.text for para in doc.paragraphs]
        elif file_extension == 'txt':
            texts = file_content.decode('utf-8').splitlines()
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type")

        answer = synthesize_answer("Extract total years of experience and skills.", texts)

        experience_match = None
        skills_match = None
        if "Years of Experience:" in answer:
            experience_match = answer.split("Years of Experience:")[1].split("\n")[0].strip()
        if "Skills:" in answer:
            skills_match = answer.split("Skills:")[1].strip()

        text = "\n".join(texts)
        embeddings = fetch_embeddings([text])

        resume_data = {
            "file_name": file.filename,
            "s3_url": f"https://{S3_BUCKET_NAME}.s3.amazonaws.com/{s3_file_path}",
            "text": text,
            "technical_skills": skills_match if skills_match else "N/A",
            "years_of_experience": experience_match if experience_match else "N/A",
            "embeddings": json.dumps(embeddings),
            "uploaded_at": datetime.datetime.utcnow()
        }

        if existing_doc:
            resume_collection.update_one({"file_name": file.filename}, {"$set": resume_data})
            print(" Updated existing record in MongoDB")
        else:
            resume_collection.insert_one(resume_data)
            print(" New record inserted in MongoDB")

        return JSONResponse(content={"document_id": file.filename, "answer": answer})

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing the document: {e}")

