import os
import io
import fitz  # PyMuPDF for PDF
import docx
import pymongo
import cohere
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from typing import List

# Load environment variables
load_dotenv()

# API Keys
COHERE_API_KEY = os.getenv("COHERE_API_KEY")

# Initialize Cohere Client
co = cohere.Client(api_key=COHERE_API_KEY)

# MongoDB Connection
client = pymongo.MongoClient("mongodb+srv://krishnasai:krishna132@cluster0.wjww1.mongodb.net/")
db = client["job_matching"]
jobs_collection = db["jobs"]
# FastAPI Instance
app = FastAPI()

def extract_text_from_file(file_content: bytes, file_extension: str) -> str:
    """Extracts text from PDF, DOCX, and TXT files."""
    text = ""
    if file_extension == "pdf":
        doc = fitz.open(stream=file_content, filetype="pdf")
        text = "\n".join([page.get_text() for page in doc])
    elif file_extension == "docx":
        doc = docx.Document(io.BytesIO(file_content))
        text = "\n".join([para.text for para in doc.paragraphs])
    elif file_extension == "txt":
        text = file_content.decode("utf-8")
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    return text.strip()

def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """Generates text embeddings using Cohere API."""
    try:
        embeddings = co.embed(texts=texts, model="embed-english-v3.0", input_type="search_document").embeddings
        return embeddings
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate embeddings: {e}")

@app.post("/upload_job_descriptions/")
async def upload_job_descriptions(file: UploadFile = File(...)):
    """Handles job description uploads, extracts text, and stores data in MongoDB."""
    try:
        file_extension = file.filename.split(".")[-1].lower()
        file_content = await file.read()

        # Extract text
        job_text = extract_text_from_file(file_content, file_extension)

        # Generate embeddings
        embeddings = generate_embeddings([job_text])

        # Store job description in MongoDB
        job_data = {
            "file_name": file.filename,
            "text": job_text,
            "embedding": embeddings,
        }
        jobs_collection.insert_one(job_data)

        return JSONResponse(content={"message": "Job description uploaded successfully!", "file_name": file.filename})

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing job description: {e}")
