from pymongo import MongoClient
import os
from dotenv import load_dotenv
from datetime import datetime
from typing import List, Optional
from fastapi import UploadFile, HTTPException
from cloudinary.uploader import upload

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")

def get_db():
    """Get MongoDB database connection with error handling"""
    if not MONGO_URI:
        print("Warning: MONGO_URI environment variable is not set")
        return None
    
    try:
        if "mongodb+srv" in MONGO_URI:
            client = MongoClient(
                MONGO_URI,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
                socketTimeoutMS=5000,
                retryWrites=True,
                tlsAllowInvalidCertificates=False,
            )
        elif "mongodb.net" in MONGO_URI and "mongodb://" in MONGO_URI:
            uri_with_params = MONGO_URI
            if "?" not in uri_with_params:
                uri_with_params += "?retryWrites=true&w=majority"
            elif "retryWrites" not in uri_with_params:
                uri_with_params += "&retryWrites=true"
            
            client = MongoClient(
                uri_with_params,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
                socketTimeoutMS=5000,
                retryWrites=True,
                tls=True,
                tlsAllowInvalidCertificates=False,
            )
        else:
            client = MongoClient(
                MONGO_URI,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
                socketTimeoutMS=5000,
            )
        
        client.admin.command('ping')
        print("✅ MongoDB connection successful!")
        return client["statm8"]
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        print(f"⚠️  MongoDB connection error: {error_type}")
        
        if "SSL" in error_msg or "TLS" in error_msg or "handshake" in error_msg:
            print("   SSL/TLS connection issue detected.")
            print("   Suggested fixes:")
            print("   1. Use 'mongodb+srv://' instead of 'mongodb://' for MongoDB Atlas")
            print("   2. Ensure connection string format: mongodb+srv://user:pass@cluster.mongodb.net/dbname?retryWrites=true&w=majority")
            print("   3. Check IP whitelist in MongoDB Atlas Dashboard")
            print("   4. Verify username and password are URL-encoded")
        elif "authentication" in error_msg.lower():
            print("   Authentication issue detected.")
            print("   Check username and password in connection string")
        elif "timeout" in error_msg.lower():
            print("   Connection timeout detected.")
            print("   Check network connectivity and IP whitelist")
        
        print("   Application will continue without database. Files will be saved locally only.")
        return None

db = get_db()

csv_collection = db["csv_files"] if db is not None else None
comment_collection = db["comments"] if db is not None else None
asset_collection = db["comment_assets"] if db is not None else None

# ---------------- CSV Upload ----------------
async def upload_csv_file(uid: str, csv_name: str, json_response: str, csv_file: UploadFile):
    if csv_collection is None:
        raise HTTPException(status_code=503, detail="Database connection not available")
    
    csv_url = f"local://uploads/{csv_name}"
    try:
        csv_upload = upload(
            csv_file.file,
            folder="csv_files",
            resource_type="raw"
        )
        csv_url = csv_upload.get("secure_url", csv_url)
    except Exception as e:
        print(f"Cloudinary upload failed: {e}. Will use local file path.")
        csv_url = f"local://uploads/{csv_name}"

    doc = {
        "uid": uid,
        "csv_name": csv_name,
        "csv_url": csv_url,
        "json_response": json_response,
        "created_at": datetime.utcnow()
    }

    try:
        result = csv_collection.insert_one(doc)
        return {"csv_id": str(result.inserted_id)}
    except Exception as e:
        print(f"MongoDB insert failed: {e}")
        raise HTTPException(status_code=503, detail=f"Database operation failed: {str(e)}")

# ---------------- Add Comment ----------------
def add_csv_comment(uid: str, csv_id: str, comment: str):
    if comment_collection is None:
        raise HTTPException(status_code=503, detail="Database connection not available")
    
    doc = {
        "uid": uid,
        "csv_id": csv_id,
        "comment": comment,
        "created_at": datetime.utcnow()
    }

    result = comment_collection.insert_one(doc)
    return {"comment_id": str(result.inserted_id)}

# ---------------- Add Comment Asset ----------------
async def add_comment_assets(comment_id: str, code: str, description: str, images: List[UploadFile]):
    if asset_collection is None:
        raise HTTPException(status_code=503, detail="Database connection not available")
    
    image_urls = []

    for image in images:
        upload_result = upload(
            image.file,
            folder="comment_images",
        )
        image_urls.append(upload_result["secure_url"])

    doc = {
        "comment_id": comment_id,
        "code": code,
        "image_urls": image_urls,
        "created_at": datetime.utcnow()
    }

    asset_collection.insert_one(doc)

    return {
        "message": "Code block with multiple images added",
        "image_count": len(image_urls)
    }
