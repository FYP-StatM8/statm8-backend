from pymongo import MongoClient
import os
from dotenv import load_dotenv
from datetime import datetime
from typing import List
from fastapi import UploadFile
from cloudinary.uploader import upload

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")

client = MongoClient(MONGO_URI)
db = client["statm8"]

csv_collection = db["csv_files"]
comment_collection = db["comments"]
asset_collection = db["comment_assets"]

# ---------------- CSV Upload ----------------
async def upload_csv_file(uid: str, csv_name: str, json_response: str, csv_file: UploadFile):
    csv_upload = upload(
        csv_file.file,
        folder="csv_files",
        resource_type="raw"
    )

    doc = {
        "uid": uid,
        "csv_name": csv_name,
        "csv_url": csv_upload["secure_url"],
        "json_response": json_response,
        "created_at": datetime.utcnow()
    }

    result = csv_collection.insert_one(doc)
    return {"csv_id": str(result.inserted_id)}

# ---------------- Add Comment ----------------
def add_csv_comment(uid: str, csv_id: str, comment: str):
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
