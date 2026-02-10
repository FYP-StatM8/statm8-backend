from pymongo import MongoClient
from bson.objectid import ObjectId
import os
import io
import hashlib
from dotenv import load_dotenv
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from fastapi import UploadFile, HTTPException
from cloudinary.uploader import upload

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")

def get_db():
    """
    Get MongoDB database connection. 
    MongoDB is REQUIRED - raises RuntimeError if connection fails.
    """
    if not MONGO_URI:
        raise RuntimeError(
            "MONGO_URI environment variable is not set. "
            "MongoDB is required for this application."
        )
    
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
        
        error_details = f"MongoDB connection failed: {error_type} - {error_msg}\n"
        
        if "SSL" in error_msg or "TLS" in error_msg or "handshake" in error_msg:
            error_details += (
                "SSL/TLS connection issue detected.\n"
                "Suggested fixes:\n"
                "1. Use 'mongodb+srv://' instead of 'mongodb://' for MongoDB Atlas\n"
                "2. Ensure connection string format: mongodb+srv://user:pass@cluster.mongodb.net/dbname?retryWrites=true&w=majority\n"
                "3. Check IP whitelist in MongoDB Atlas Dashboard\n"
                "4. Verify username and password are URL-encoded"
            )
        elif "authentication" in error_msg.lower():
            error_details += "Authentication issue. Check username and password in connection string."
        elif "timeout" in error_msg.lower():
            error_details += "Connection timeout. Check network connectivity and IP whitelist."
        
        raise RuntimeError(error_details)

db = get_db()

# MongoDB collections - always available since connection is required
csv_collection = db["csv_files"]
comment_collection = db["comments"]
asset_collection = db["comment_assets"]
vlm_collection = db["vlm_analyses"]
export_collection = db["exports"]
plots_collection = db["plots"]  # New collection for storing plot metadata and URLs

# ---------------- CSV Upload ----------------
async def upload_csv_file(uid: str, csv_name: str, json_response: str, csv_file: UploadFile):
    """Upload CSV file to Cloudinary and store metadata in MongoDB."""
    try:
        csv_upload = upload(
            csv_file.file,
            folder="csv_files",
            resource_type="raw",
            type="upload"
        )
        csv_url = csv_upload.get("secure_url")
        if not csv_url:
            raise HTTPException(status_code=500, detail="Cloudinary upload failed - no URL returned")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cloudinary upload failed: {str(e)}")

    doc = {
        "uid": uid,
        "csv_name": csv_name,
        "csv_url": csv_url,
        "json_response": json_response,
        "created_at": datetime.utcnow()
    }

    result = csv_collection.insert_one(doc)
    return {"csv_id": str(result.inserted_id)}


# ---------------- Plot Upload (NEW) ----------------
async def upload_plot_to_cloudinary(
    image_bytes: bytes,
    filename: str,
    dataset_name: str
) -> Dict[str, str]:
    """
    Upload a plot image to Cloudinary.
    
    Args:
        image_bytes: Raw image bytes
        filename: Name of the plot file
        dataset_name: Name of the dataset this plot belongs to
    
    Returns:
        Dict with cloudinary_url and public_id
    """
    try:
        upload_result = upload(
            io.BytesIO(image_bytes),
            folder=f"plots/{dataset_name}",
            resource_type="image",
            public_id=filename.rsplit('.', 1)[0],  # Remove extension for public_id
            overwrite=True,
            type="upload"
        )
        
        cloudinary_url = upload_result.get("secure_url", "")
        public_id = upload_result.get("public_id", "")
        
        print(f"✅ Plot uploaded to Cloudinary: {filename} -> {cloudinary_url}")
        
        return {
            "cloudinary_url": cloudinary_url,
            "public_id": public_id,
            "format": upload_result.get("format", "png")
        }
    except Exception as e:
        print(f"❌ Cloudinary plot upload failed for {filename}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Cloudinary plot upload failed: {str(e)}")


async def save_plot_to_db(
    uid: str,
    csv_id: str,
    filename: str,
    cloudinary_url: str,
    public_id: str,
    code_block_id: Optional[int] = None,
    description: Optional[str] = None,
    comment_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Save plot metadata to MongoDB.
    
    Args:
        uid: User ID
        csv_id: Associated CSV file ID (MongoDB ObjectId string)
        filename: Original filename of the plot
        cloudinary_url: URL from Cloudinary
        public_id: Cloudinary public ID
        code_block_id: ID of the code block that generated this plot
        description: Description of the plot
        comment_id: Optional comment ID for associating plot with specific analysis
    
    Returns:
        Dict with plot_id
    """
    # Get csv_name for display purposes
    csv_name = get_csv_name_by_id(csv_id)
    
    doc = {
        "uid": uid,
        "csv_id": csv_id,
        "csv_name": csv_name,  # Store for display, but query by csv_id
        "filename": filename,
        "cloudinary_url": cloudinary_url,
        "public_id": public_id,
        "code_block_id": code_block_id,
        "description": description,
        "comment_id": comment_id,
        "created_at": datetime.utcnow()
    }
    
    # Upsert based on csv_id, filename, and comment_id to avoid duplicates
    query = {"csv_id": csv_id, "filename": filename}
    if comment_id:
        query["comment_id"] = comment_id
    
    result = plots_collection.update_one(
        query,
        {"$set": doc},
        upsert=True
    )
    
    if result.upserted_id:
        return {"plot_id": str(result.upserted_id)}
    
    existing = plots_collection.find_one(query)
    return {"plot_id": str(existing["_id"]) if existing else None}


def get_plots_for_csv(csv_id: str, uid: Optional[str] = None, comment_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get all plots for a CSV file from MongoDB.
    
    Args:
        csv_id: MongoDB ObjectId string for the CSV file
        uid: Optional user ID filter
        comment_id: Optional comment ID filter (required for VLM analysis endpoints)
    
    Returns:
        List of plot documents with cloudinary URLs
    """
    query = {"csv_id": csv_id}
    if uid:
        query["uid"] = uid
    if comment_id:
        query["comment_id"] = comment_id
    
    plots = list(plots_collection.find(query).sort("created_at", 1))
    
    for plot in plots:
        plot["_id"] = str(plot["_id"])
    
    return plots


def get_plot_by_filename(csv_id: str, filename: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific plot by CSV ID and filename.
    
    Args:
        csv_id: MongoDB ObjectId string for the CSV file
        filename: Filename of the plot
    
    Returns:
        Plot document if found
    """
    plot = plots_collection.find_one({"csv_id": csv_id, "filename": filename})
    if plot:
        plot["_id"] = str(plot["_id"])
    return plot

# ---------------- Add Comment ----------------
def add_csv_comment(uid: str, csv_id: str, comment: str):
    """Add a comment to a CSV file."""
    doc = {
        "uid": uid,
        "csv_id": csv_id,
        "comment": comment,
        "created_at": datetime.utcnow()
    }

    result = comment_collection.insert_one(doc)
    return {"comment_id": str(result.inserted_id)}

# ---------------- Add Comment Asset ----------------
async def add_comment_assets(
    comment_id: str, 
    code: str, 
    description: str, 
    images: List[UploadFile],
    plot_urls: Optional[List[str]] = None
):
    """
    Add code and images to a comment.
    
    Args:
        comment_id: The comment ID to associate assets with
        code: The code block that generated the assets
        description: Description of the code block
        images: List of UploadFile images to upload to Cloudinary
        plot_urls: List of already-uploaded Cloudinary URLs for plots
    """
    image_urls = []

    # Upload any new images from UploadFile objects
    for image in images:
        upload_result = upload(
            image.file,
            folder="comment_images",
            type="upload"
        )
        image_urls.append(upload_result["secure_url"])

    # Merge with already-uploaded plot URLs
    if plot_urls:
        image_urls.extend(plot_urls)

    doc = {
        "comment_id": comment_id,
        "code": code,
        "description": description,
        "image_urls": image_urls,
        "created_at": datetime.utcnow()
    }

    asset_collection.insert_one(doc)

    return {
        "message": "Code block with multiple images added",
        "image_count": len(image_urls)
    }


# ---------------- VLM Analysis Storage ----------------
def compute_plots_hash(plot_urls: List[str]) -> str:
    """
    Compute a hash of plot URLs for cache invalidation.
    Uses URLs instead of local file paths.
    """
    if not plot_urls:
        return ""
    
    # Sort URLs for consistent hashing
    sorted_urls = sorted(plot_urls)
    return hashlib.md5("|".join(sorted_urls).encode()).hexdigest()


async def save_vlm_analysis_to_db(
    uid: str,
    csv_id: str,
    comment_id: str,
    plot_urls: List[str],
    plot_analyses: List[Dict[str, Any]],
    summary: Optional[str],
    overall_status: str
) -> Dict[str, Any]:
    """
    Save VLM analysis results to MongoDB.
    
    Args:
        uid: User ID
        csv_id: Associated CSV file ID (MongoDB ObjectId string)
        comment_id: Associated comment ID (MongoDB ObjectId string)
        plot_urls: List of Cloudinary URLs for the analyzed plots
        plot_analyses: List of per-plot analysis results
        summary: Overall VLM summary
        overall_status: Status of the analysis (completed/failed)
    
    Returns:
        Dict with vlm_analysis_id
    """
    plots_hash = compute_plots_hash(plot_urls)
    csv_name = get_csv_name_by_id(csv_id)
    
    doc = {
        "uid": uid,
        "csv_id": csv_id,
        "comment_id": comment_id,
        "csv_name": csv_name,  # Store for display purposes
        "plots_hash": plots_hash,
        "plot_urls": plot_urls,
        "plot_analyses": plot_analyses,
        "summary": summary,
        "overall_status": overall_status,
        "total_plots": len(plot_analyses),
        "successful_plots": len([p for p in plot_analyses if p.get("status") == "success"]),
        "created_at": datetime.utcnow()
    }
    
    # Upsert: update existing or insert new (keyed by csv_id + comment_id)
    result = vlm_collection.update_one(
        {"uid": uid, "csv_id": csv_id, "comment_id": comment_id},
        {"$set": doc},
        upsert=True
    )
    
    if result.upserted_id:
        return {"vlm_analysis_id": str(result.upserted_id), "cached": False}
    
    # If updated existing, get the ID
    existing = vlm_collection.find_one({"uid": uid, "csv_id": csv_id, "comment_id": comment_id})
    return {"vlm_analysis_id": str(existing["_id"]) if existing else None, "cached": False}


def get_vlm_analysis_from_db(
    uid: str,
    csv_id: str,
    comment_id: str,
    current_plot_urls: Optional[List[str]] = None
) -> Optional[Dict[str, Any]]:
    """
    Retrieve VLM analysis from MongoDB.
    Optionally validates that plots haven't changed using hash.
    
    Args:
        uid: User ID
        csv_id: Associated CSV file ID (MongoDB ObjectId string)
        comment_id: Associated comment ID (MongoDB ObjectId string)
        current_plot_urls: If provided, validates cache freshness
    
    Returns:
        VLM analysis data if found and valid, None otherwise
    """
    analysis = vlm_collection.find_one({
        "uid": uid,
        "csv_id": csv_id,
        "comment_id": comment_id
    })
    
    if not analysis:
        return None
    
    # Validate cache if current plot URLs provided
    if current_plot_urls:
        current_hash = compute_plots_hash(current_plot_urls)
        if analysis.get("plots_hash") != current_hash:
            # Plots have changed, cache is stale
            return None
    
    # Convert ObjectId to string for JSON serialization
    analysis["_id"] = str(analysis["_id"])
    return analysis


def get_vlm_analysis_by_csv(csv_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve the latest VLM analysis for a CSV file (without uid filtering).
    Useful for export service which may not have user context.
    
    Args:
        csv_id: MongoDB ObjectId string for the CSV file
    
    Returns:
        Latest VLM analysis data if found, None otherwise
    """
    analysis = vlm_collection.find_one(
        {"csv_id": csv_id},
        sort=[("created_at", -1)]
    )
    
    if not analysis:
        return None
    
    analysis["_id"] = str(analysis["_id"])
    return analysis


# ---------------- Export Storage ----------------
async def upload_export_to_cloudinary(
    file_bytes: bytes,
    filename: str,
    csv_id: str,
    export_format: str
) -> Dict[str, str]:
    """
    Upload an export file (PDF, ZIP, etc.) to Cloudinary.
    
    Args:
        file_bytes: Raw bytes of the file
        filename: Name for the file
        csv_id: MongoDB ObjectId string for the CSV file
        export_format: Format of export (pdf, markdown, latex)
    
    Returns:
        Dict with cloudinary_url and public_id
    """
    try:
        folder = f"exports/{csv_id}"
        
        upload_result = upload(
            io.BytesIO(file_bytes),
            folder=folder,
            resource_type="raw",
            public_id=filename,
            overwrite=True,
            access_mode="public",
            type="upload",
            use_filename=True,
            unique_filename=False
        )
        
        return {
            "cloudinary_url": upload_result.get("secure_url", ""),
            "public_id": upload_result.get("public_id", ""),
            "format": export_format
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cloudinary export upload failed: {str(e)}")


async def save_export_to_db(
    uid: str,
    csv_id: str,
    vlm_analysis_id: str,
    export_format: str,
    cloudinary_url: str,
    public_id: str,
    file_size_bytes: int,
    sections_included: List[str],
    total_plots: int
) -> Dict[str, Any]:
    """
    Save export metadata to MongoDB.
    
    Args:
        uid: User ID
        csv_id: Associated CSV file ID (MongoDB ObjectId string)
        vlm_analysis_id: Associated VLM analysis ID (MongoDB ObjectId string)
        export_format: Format (pdf, markdown, latex)
        cloudinary_url: URL from Cloudinary
        public_id: Cloudinary public ID
        file_size_bytes: Size of the export file
        sections_included: List of sections in the export
        total_plots: Number of plots included
    
    Returns:
        Dict with export_id and download_url
    """
    csv_name = get_csv_name_by_id(csv_id)
    
    doc = {
        "uid": uid,
        "csv_id": csv_id,
        "vlm_analysis_id": vlm_analysis_id,
        "csv_name": csv_name,  # Store for display purposes
        "format": export_format,
        "cloudinary_url": cloudinary_url,
        "public_id": public_id,
        "file_size_bytes": file_size_bytes,
        "sections_included": sections_included,
        "total_plots": total_plots,
        "created_at": datetime.utcnow()
    }
    
    result = export_collection.insert_one(doc)
    
    return {
        "export_id": str(result.inserted_id),
        "download_url": cloudinary_url
    }


def get_export_by_id(export_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve an export record by ID.
    
    Args:
        export_id: MongoDB ObjectId as string
    
    Returns:
        Export document if found
    """
    try:
        export = export_collection.find_one({"_id": ObjectId(export_id)})
        if export:
            export["_id"] = str(export["_id"])
        return export
    except Exception:
        return None


def get_user_exports(uid: str, csv_id: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Get export history for a user.
    
    Args:
        uid: User ID
        csv_id: Optional filter by CSV file
        limit: Maximum number of results
    
    Returns:
        List of export documents
    """
    query = {"uid": uid}
    if csv_id:
        query["csv_id"] = csv_id
    
    exports = list(export_collection.find(query).sort("created_at", -1).limit(limit))
    
    for export in exports:
        export["_id"] = str(export["_id"])
    
    return exports


# ---------------- Dataset Summary Storage ----------------
def save_dataset_summary_to_db(
    uid: str,
    csv_id: str,
    csv_name: str,
    summary_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Update the CSV document with dataset summary data.
    
    Args:
        uid: User ID
        csv_id: MongoDB ObjectId of the CSV document
        csv_name: Name of the CSV file
        summary_data: The dataset summary (columns_info, ai_summary, etc.)
    
    Returns:
        Dict with success status
    """
    result = csv_collection.update_one(
        {"_id": ObjectId(csv_id)},
        {"$set": {"summary_data": summary_data, "updated_at": datetime.utcnow()}}
    )
    
    return {"updated": result.modified_count > 0}


def get_dataset_summary_from_db(csv_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve dataset summary from MongoDB.
    
    Args:
        csv_id: MongoDB ObjectId as string
    
    Returns:
        Summary data if found
    """
    try:
        doc = csv_collection.find_one({"_id": ObjectId(csv_id)})
        if doc and "summary_data" in doc:
            return doc["summary_data"]
        if doc and "json_response" in doc:
            # Fallback to json_response field
            import json
            return json.loads(doc["json_response"])
        return None
    except Exception:
        return None


def get_csv_by_name(csv_name: str, uid: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Get CSV document by name.
    
    Args:
        csv_name: Name of the CSV file (without extension)
        uid: Optional user ID filter
    
    Returns:
        CSV document if found
    """
    query = {"csv_name": csv_name}
    if uid:
        query["uid"] = uid
    
    doc = csv_collection.find_one(query, sort=[("created_at", -1)])
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


def get_csv_by_id(csv_id: str) -> Optional[Dict[str, Any]]:
    """
    Get CSV document by its MongoDB ID.
    
    Args:
        csv_id: MongoDB ObjectId as string
    
    Returns:
        CSV document if found
    """
    try:
        doc = csv_collection.find_one({"_id": ObjectId(csv_id)})
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc
    except Exception:
        return None


def get_csv_name_by_id(csv_id: str) -> Optional[str]:
    """
    Get the csv_name from a csv_id.
    
    Args:
        csv_id: MongoDB ObjectId as string
    
    Returns:
        csv_name if found, None otherwise
    """
    doc = get_csv_by_id(csv_id)
    return doc.get("csv_name") if doc else None


async def fetch_csv_bytes_from_cloudinary(csv_url: str) -> bytes:
    """
    Fetch CSV file bytes from Cloudinary URL.
    
    Args:
        csv_url: Cloudinary URL for the CSV file
    
    Returns:
        Raw bytes of the CSV file
    """
    import httpx
    async with httpx.AsyncClient() as client:
        response = await client.get(csv_url)
        response.raise_for_status()
        return response.content


async def get_csv_file_for_processing(csv_id: str) -> Tuple[bytes, str]:
    """
    Get CSV file bytes from Cloudinary for processing.
    
    Args:
        csv_id: MongoDB ObjectId of the CSV document
    
    Returns:
        Tuple of (csv_bytes, csv_name)
    
    Raises:
        HTTPException if CSV not found
    """
    doc = get_csv_by_id(csv_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"CSV file not found: {csv_id}")
    
    csv_url = doc.get("csv_url")
    if not csv_url:
        raise HTTPException(status_code=500, detail=f"CSV file has no Cloudinary URL: {csv_id}")
    
    csv_name = doc.get("csv_name")
    csv_bytes = await fetch_csv_bytes_from_cloudinary(csv_url)
    return csv_bytes, csv_name


def get_all_vlm_analyses_for_csv(csv_id: str, uid: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get all VLM analyses for a given CSV file.
    
    Args:
        csv_id: The ID of the CSV file
        uid: Optional user ID to filter analyses by user
    
    Returns:
        List of VLM analysis documents, sorted by created_at descending
    """
    query = {"csv_id": csv_id}
    if uid:
        query["uid"] = uid
    
    analyses = list(vlm_collection.find(query).sort("created_at", -1))
    for analysis in analyses:
        analysis["_id"] = str(analysis["_id"])
    return analyses
