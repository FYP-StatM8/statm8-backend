from pymongo import MongoClient
from bson.objectid import ObjectId
import os
import hashlib
from dotenv import load_dotenv
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import UploadFile, HTTPException
from cloudinary.uploader import upload
import cloudinary.utils

load_dotenv()

# Cloudinary signed URL expiration (7 days)
CLOUDINARY_URL_EXPIRATION_DAYS = 7

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
vlm_collection = db["vlm_analyses"] if db is not None else None
export_collection = db["exports"] if db is not None else None

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


# ---------------- VLM Analysis Storage ----------------
def compute_plots_hash(plot_dir: str) -> str:
    """
    Compute a hash of plot files in a directory for cache invalidation.
    Uses filenames and modification times.
    """
    if not os.path.exists(plot_dir):
        return ""
    
    plot_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
    plot_info = []
    
    for filename in sorted(os.listdir(plot_dir)):
        ext = os.path.splitext(filename)[1].lower()
        if ext in plot_extensions:
            filepath = os.path.join(plot_dir, filename)
            mtime = os.path.getmtime(filepath)
            plot_info.append(f"{filename}:{mtime}")
    
    return hashlib.md5("|".join(plot_info).encode()).hexdigest()


async def save_vlm_analysis_to_db(
    uid: str,
    csv_id: str,
    dataset_name: str,
    plot_dir: str,
    plot_analyses: List[Dict[str, Any]],
    summary: Optional[str],
    overall_status: str
) -> Dict[str, Any]:
    """
    Save VLM analysis results to MongoDB for persistence.
    
    Args:
        uid: User ID
        csv_id: Associated CSV file ID
        dataset_name: Name of the dataset
        plot_dir: Path to plot directory (for hash computation)
        plot_analyses: List of per-plot analysis results
        summary: Overall VLM summary
        overall_status: Status of the analysis (completed/failed)
    
    Returns:
        Dict with vlm_analysis_id
    """
    if vlm_collection is None:
        # Gracefully handle missing DB - return empty response
        print("Warning: VLM analysis not saved - database not available")
        return {"vlm_analysis_id": None, "cached": False}
    
    plots_hash = compute_plots_hash(plot_dir)
    
    doc = {
        "uid": uid,
        "csv_id": csv_id,
        "dataset_name": dataset_name,
        "plots_hash": plots_hash,
        "plot_analyses": plot_analyses,
        "summary": summary,
        "overall_status": overall_status,
        "total_plots": len(plot_analyses),
        "successful_plots": len([p for p in plot_analyses if p.get("status") == "success"]),
        "created_at": datetime.utcnow()
    }
    
    # Upsert: update existing or insert new
    result = vlm_collection.update_one(
        {"uid": uid, "csv_id": csv_id, "dataset_name": dataset_name},
        {"$set": doc},
        upsert=True
    )
    
    if result.upserted_id:
        return {"vlm_analysis_id": str(result.upserted_id), "cached": False}
    
    # If updated existing, get the ID
    existing = vlm_collection.find_one({"uid": uid, "csv_id": csv_id, "dataset_name": dataset_name})
    return {"vlm_analysis_id": str(existing["_id"]) if existing else None, "cached": False}


def get_vlm_analysis_from_db(
    uid: str,
    csv_id: str,
    dataset_name: str,
    plot_dir: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Retrieve VLM analysis from MongoDB.
    Optionally validates that plots haven't changed using hash.
    
    Args:
        uid: User ID
        csv_id: Associated CSV file ID
        dataset_name: Name of the dataset
        plot_dir: If provided, validates cache freshness
    
    Returns:
        VLM analysis data if found and valid, None otherwise
    """
    if vlm_collection is None:
        return None
    
    analysis = vlm_collection.find_one({
        "uid": uid,
        "csv_id": csv_id,
        "dataset_name": dataset_name
    })
    
    if not analysis:
        return None
    
    # Validate cache if plot_dir provided
    if plot_dir:
        current_hash = compute_plots_hash(plot_dir)
        if analysis.get("plots_hash") != current_hash:
            # Plots have changed, cache is stale
            return None
    
    # Convert ObjectId to string for JSON serialization
    analysis["_id"] = str(analysis["_id"])
    return analysis


def get_vlm_analysis_by_dataset(dataset_name: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve the latest VLM analysis for a dataset (without uid/csv_id filtering).
    Useful for export service which may not have user context.
    
    Args:
        dataset_name: Name of the dataset
    
    Returns:
        Latest VLM analysis data if found, None otherwise
    """
    if vlm_collection is None:
        return None
    
    analysis = vlm_collection.find_one(
        {"dataset_name": dataset_name},
        sort=[("created_at", -1)]
    )
    
    if not analysis:
        return None
    
    analysis["_id"] = str(analysis["_id"])
    return analysis


# ---------------- Export Storage ----------------
def generate_signed_cloudinary_url(public_id: str, resource_type: str = "raw") -> str:
    """
    Generate a signed Cloudinary URL with expiration.
    
    Args:
        public_id: Cloudinary public ID of the resource
        resource_type: Type of resource (raw, image, video)
    
    Returns:
        Signed URL with 7-day expiration
    """
    expiration_timestamp = int((datetime.utcnow() + timedelta(days=CLOUDINARY_URL_EXPIRATION_DAYS)).timestamp())
    
    signed_url = cloudinary.utils.cloudinary_url(
        public_id,
        resource_type=resource_type,
        sign_url=True,
        type="authenticated",
        expires_at=expiration_timestamp
    )[0]
    
    return signed_url


async def upload_export_to_cloudinary(
    file_path: str,
    dataset_name: str,
    export_format: str
) -> Dict[str, str]:
    """
    Upload an export file (PDF or ZIP) to Cloudinary.
    
    Args:
        file_path: Local path to the file
        dataset_name: Name of the dataset
        export_format: Format of export (pdf, markdown, latex)
    
    Returns:
        Dict with cloudinary_url and public_id
    """
    try:
        # Determine resource type and folder
        filename = os.path.basename(file_path)
        folder = f"exports/{dataset_name}"
        
        with open(file_path, "rb") as f:
            upload_result = upload(
                f,
                folder=folder,
                resource_type="raw",
                public_id=os.path.splitext(filename)[0],
                overwrite=True
            )
        
        return {
            "cloudinary_url": upload_result.get("secure_url", ""),
            "public_id": upload_result.get("public_id", ""),
            "format": export_format
        }
    except Exception as e:
        print(f"Cloudinary upload failed for export: {e}")
        return {
            "cloudinary_url": None,
            "public_id": None,
            "format": export_format,
            "error": str(e)
        }


async def save_export_to_db(
    uid: str,
    csv_id: str,
    dataset_name: str,
    export_format: str,
    cloudinary_url: Optional[str],
    public_id: Optional[str],
    file_size_bytes: int,
    sections_included: List[str],
    total_plots: int,
    local_path: str
) -> Dict[str, Any]:
    """
    Save export metadata to MongoDB.
    
    Args:
        uid: User ID
        csv_id: Associated CSV file ID
        dataset_name: Name of the dataset
        export_format: Format (pdf, markdown, latex)
        cloudinary_url: URL from Cloudinary (may be None if upload failed)
        public_id: Cloudinary public ID for generating new signed URLs
        file_size_bytes: Size of the export file
        sections_included: List of sections in the export
        total_plots: Number of plots included
        local_path: Local filesystem path (fallback)
    
    Returns:
        Dict with export_id and download_url
    """
    if export_collection is None:
        print("Warning: Export not saved to DB - database not available")
        return {
            "export_id": None,
            "download_url": cloudinary_url or f"local://{local_path}"
        }
    
    doc = {
        "uid": uid,
        "csv_id": csv_id,
        "dataset_name": dataset_name,
        "format": export_format,
        "cloudinary_url": cloudinary_url,
        "public_id": public_id,
        "file_size_bytes": file_size_bytes,
        "sections_included": sections_included,
        "total_plots": total_plots,
        "local_path": local_path,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(days=CLOUDINARY_URL_EXPIRATION_DAYS) if cloudinary_url else None
    }
    
    result = export_collection.insert_one(doc)
    
    return {
        "export_id": str(result.inserted_id),
        "download_url": cloudinary_url or f"local://{local_path}"
    }


def get_export_by_id(export_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve an export record by ID.
    
    Args:
        export_id: MongoDB ObjectId as string
    
    Returns:
        Export document if found
    """
    if export_collection is None:
        return None
    
    try:
        export = export_collection.find_one({"_id": ObjectId(export_id)})
        if export:
            export["_id"] = str(export["_id"])
        return export
    except Exception:
        return None


def get_user_exports(uid: str, dataset_name: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Get export history for a user.
    
    Args:
        uid: User ID
        dataset_name: Optional filter by dataset
        limit: Maximum number of results
    
    Returns:
        List of export documents
    """
    if export_collection is None:
        return []
    
    query = {"uid": uid}
    if dataset_name:
        query["dataset_name"] = dataset_name
    
    exports = list(export_collection.find(query).sort("created_at", -1).limit(limit))
    
    for export in exports:
        export["_id"] = str(export["_id"])
    
    return exports


def regenerate_export_url(export_id: str) -> Optional[str]:
    """
    Regenerate a signed Cloudinary URL for an existing export.
    Used when the original URL has expired.
    
    Args:
        export_id: MongoDB ObjectId as string
    
    Returns:
        New signed URL or None if not possible
    """
    if export_collection is None:
        return None
    
    try:
        export = export_collection.find_one({"_id": ObjectId(export_id)})
        if not export or not export.get("public_id"):
            return None
        
        new_url = generate_signed_cloudinary_url(export["public_id"])
        
        # Update the stored URL and expiration
        export_collection.update_one(
            {"_id": ObjectId(export_id)},
            {
                "$set": {
                    "cloudinary_url": new_url,
                    "expires_at": datetime.utcnow() + timedelta(days=CLOUDINARY_URL_EXPIRATION_DAYS)
                }
            }
        )
        
        return new_url
    except Exception as e:
        print(f"Failed to regenerate export URL: {e}")
        return None
