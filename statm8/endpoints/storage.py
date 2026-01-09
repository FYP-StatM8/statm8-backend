from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from datetime import datetime
import uuid
from bson import ObjectId
from typing import List

from cloudinary.uploader import upload

from config.cloudinary import cloudinary
from statm8.services.storage import (
    csv_collection,
    comment_collection,
    asset_collection,
    upload_csv_file, 
    add_csv_comment, 
    add_comment_assets
)

router = APIRouter(prefix="/storage", tags=["Storage"])

# ---------------- POST ROUTES ----------------


@router.post("/csv/upload")
async def upload_csv(
    uid: str = Form(...),
    csv_name: str = Form(...),
    json_response: str = Form(...),
    csv_file: UploadFile = File(...)
):
    return await upload_csv_file(uid, csv_name, json_response, csv_file)


@router.post("/csv/comment")
def add_comment(
    uid: str = Form(...),
    csv_id: str = Form(...),
    comment: str = Form(...)
):
    return add_csv_comment(uid, csv_id, comment)


@router.post("/csv/comment/asset")
async def add_comment_asset(
    comment_id: str = Form(...),
    code: str = Form(...),
    description: str = Form(...),
    images: List[UploadFile] = File(...)
):
    return await add_comment_assets(comment_id, code, description, images)


# get routes #

@router.get("/csv/user/{uid}")
def get_user_csvs(uid: str):
    csvs = list(csv_collection.find({"uid": uid}))
    for csv_doc in csvs:
        csv_doc["_id"] = str(csv_doc["_id"])  # Convert ObjectId to string
    return {"csvs": csvs}


@router.get("/csv/{csv_id}/comments")
def get_csv_comments(csv_id: str):
    if not ObjectId.is_valid(csv_id):
        raise HTTPException(status_code=400, detail="Invalid CSV ID")

    comments = list(comment_collection.find({"csv_id": csv_id}))
    for comment_doc in comments:
        comment_doc["_id"] = str(comment_doc["_id"])
    return {"comments": comments}


@router.get("/csv/comment/{comment_id}/assets")
def get_comment_assets(comment_id: str):
    if not ObjectId.is_valid(comment_id):
        raise HTTPException(status_code=400, detail="Invalid Comment ID")

    assets = list(asset_collection.find({"comment_id": comment_id}))
    for asset_doc in assets:
        asset_doc["_id"] = str(asset_doc["_id"])
    return {"assets": assets}
