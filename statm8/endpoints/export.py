from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from statm8.models.export import ExportRequest, ExportResponse, ExportStatusResponse, ExportListResponse
from statm8.services.export import (
    generate_pdf_report_with_upload,
    generate_markdown_report_with_upload,
    generate_latex_report_with_upload,
    check_export_status
)
from statm8.services.storage import (
    get_user_exports,
    get_export_by_id,
    get_csv_name_by_id,
    get_exports_by_csv_and_uid
)

router = APIRouter(tags=["Export"])


@router.get("/export/status/{csv_id}", response_model=ExportStatusResponse)
async def get_export_status(
    csv_id: str,
    uid: Optional[str] = Query(None, description="User ID for filtering")
):
    """
    Check what data is available for export for a given CSV file.
    
    Args:
        csv_id: MongoDB ObjectId string for the CSV file
        uid: Optional user ID for filtering data
    
    Returns:
        Status information about available data for export
    """
    status = check_export_status(csv_id, uid)
    
    if not status.can_export:
        csv_name = get_csv_name_by_id(csv_id)
        raise HTTPException(
            status_code=404,
            detail=f"No exportable data found for CSV: {csv_name}. Run data loading and/or EDA generation first."
        )
    
    return status


@router.post("/export", response_model=ExportResponse)
async def export_report(request: ExportRequest):
    """
    Generate a report for the EDA results and upload to Cloudinary.
    
    - PDF: Uploads directly to Cloudinary and returns download URL
    - Markdown/LaTeX: Creates a ZIP with the report + images, uploads to Cloudinary
    
    Requires uid and csv_id for cloud storage.
    
    Args:
        request: Export configuration including csv_id, format, and what to include
    
    Returns:
        ExportResponse with download_url (Cloudinary) and export_id (MongoDB)
    """
    # Check if there's data to export
    status = check_export_status(request.csv_id, request.uid)
    
    if not status.can_export:
        csv_name = get_csv_name_by_id(request.csv_id)
        raise HTTPException(
            status_code=404,
            detail=f"No exportable data found for CSV: {csv_name}"
        )
    
    try:
        if request.format == "markdown":
            result = await generate_markdown_report_with_upload(
                uid=request.uid,
                csv_id=request.csv_id,
                vlm_analysis_id=request.vlm_analysis_id,
                include_summary=request.include_summary,
                include_plots=request.include_plots,
                include_code=request.include_code,
                custom_title=request.title
            )
        elif request.format == "latex":
            result = await generate_latex_report_with_upload(
                uid=request.uid,
                csv_id=request.csv_id,
                vlm_analysis_id=request.vlm_analysis_id,
                include_summary=request.include_summary,
                include_plots=request.include_plots,
                include_code=request.include_code,
                custom_title=request.title
            )
        else:  # pdf
            result = await generate_pdf_report_with_upload(
                uid=request.uid,
                csv_id=request.csv_id,
                vlm_analysis_id=request.vlm_analysis_id,
                include_summary=request.include_summary,
                include_plots=request.include_plots,
                include_code=request.include_code,
                custom_title=request.title
            )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate report: {str(e)}"
        )


# ---------------- Cloud Storage Endpoints ----------------

@router.get("/export/history/{uid}")
async def get_export_history(
    uid: str,
    csv_id: Optional[str] = Query(None, description="Filter by CSV file ID"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of results")
):
    """
    Get export history for a user from MongoDB.
    
    Args:
        uid: User ID
        csv_id: Optional filter by CSV file
        limit: Maximum number of results (default 20, max 100)
    
    Returns:
        List of past exports with download URLs
    """
    exports = get_user_exports(uid, csv_id, limit)
    
    return {
        "uid": uid,
        "csv_id": csv_id,
        "exports": exports,
        "total": len(exports)
    }


@router.get("/export/by-id/{export_id}")
async def get_export_by_export_id(export_id: str):
    """
    Get a specific export by its MongoDB ID.
    
    Args:
        export_id: MongoDB ObjectId as string
    
    Returns:
        Export document with download URL
    """
    export = get_export_by_id(export_id)
    
    if not export:
        raise HTTPException(
            status_code=404,
            detail=f"Export not found: {export_id}"
        )
    
    return export


@router.get("/export/csv/{csv_id}", response_model=ExportListResponse)
async def get_exports_for_csv(
    csv_id: str,
    uid: str = Query(..., description="User ID (required)"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of results")
):
    """
    Get all exports for a specific CSV file and user.
    
    Args:
        csv_id: MongoDB ObjectId string for the CSV file
        uid: User ID (required)
        limit: Maximum number of results (default 20, max 100)
    
    Returns:
        List of exports with download URLs
    """
    exports = get_exports_by_csv_and_uid(csv_id, uid, limit)
    
    return ExportListResponse(
        csv_id=csv_id,
        uid=uid,
        exports=exports,
        total=len(exports)
    )
