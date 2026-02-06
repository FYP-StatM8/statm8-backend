from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from statm8.models.export import ExportRequest, ExportResponse, ExportStatusResponse
from statm8.services.export import (
    generate_pdf_report,
    generate_pdf_report_with_upload,
    generate_markdown_report,
    generate_markdown_report_with_upload,
    generate_latex_report,
    generate_latex_report_with_upload,
    check_export_status,
    get_dataset_paths
)
from statm8.services.storage import (
    get_user_exports,
    get_export_by_id,
    regenerate_export_url
)
import os

router = APIRouter(tags=["Export"])


@router.get("/export/status/{dataset_name}", response_model=ExportStatusResponse)
async def get_export_status(dataset_name: str):
    """
    Check what data is available for export for a given dataset.
    
    Args:
        dataset_name: Name of the dataset (e.g., 'iris', 'breast-cancer')
    
    Returns:
        Status information about available data for export
    """
    status = check_export_status(dataset_name)
    
    if not status.can_export:
        raise HTTPException(
            status_code=404,
            detail=f"No exportable data found for dataset: {dataset_name}. Run data loading and/or EDA generation first."
        )
    
    return status


@router.post("/export/pdf", response_model=ExportResponse)
async def export_to_pdf(request: ExportRequest):
    """
    Generate a PDF report for the EDA results.
    
    Args:
        request: Export configuration including dataset name and what to include
    
    Returns:
        ExportResponse with path to the generated PDF
    """
    # Check if there's data to export
    status = check_export_status(request.dataset_name)
    
    if not status.can_export:
        raise HTTPException(
            status_code=404,
            detail=f"No exportable data found for dataset: {request.dataset_name}"
        )
    
    try:
        result = generate_pdf_report(
            dataset_name=request.dataset_name,
            include_summary=request.include_summary,
            include_plots=request.include_plots,
            include_vlm_analysis=request.include_vlm_analysis,
            include_code=request.include_code,
            custom_title=request.title
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate PDF report: {str(e)}"
        )


@router.post("/export/markdown", response_model=ExportResponse)
async def export_to_markdown(request: ExportRequest):
    """
    Generate a Markdown report for the EDA results.
    Preserves original AI-generated markdown formatting.
    
    Args:
        request: Export configuration including dataset name and what to include
    
    Returns:
        ExportResponse with path to the generated Markdown file
    """
    # Check if there's data to export
    status = check_export_status(request.dataset_name)
    
    if not status.can_export:
        raise HTTPException(
            status_code=404,
            detail=f"No exportable data found for dataset: {request.dataset_name}"
        )
    
    try:
        result = generate_markdown_report(
            dataset_name=request.dataset_name,
            include_summary=request.include_summary,
            include_plots=request.include_plots,
            include_vlm_analysis=request.include_vlm_analysis,
            include_code=request.include_code,
            custom_title=request.title
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate Markdown report: {str(e)}"
        )


@router.post("/export/latex", response_model=ExportResponse)
async def export_to_latex(request: ExportRequest):
    """
    Generate a LaTeX report for the EDA results.
    Uses the report document class with Jinja2 templating.
    
    Args:
        request: Export configuration including dataset name and what to include
    
    Returns:
        ExportResponse with path to the generated LaTeX (.tex) file
    """
    # Check if there's data to export
    status = check_export_status(request.dataset_name)
    
    if not status.can_export:
        raise HTTPException(
            status_code=404,
            detail=f"No exportable data found for dataset: {request.dataset_name}"
        )
    
    try:
        result = generate_latex_report(
            dataset_name=request.dataset_name,
            include_summary=request.include_summary,
            include_plots=request.include_plots,
            include_vlm_analysis=request.include_vlm_analysis,
            include_code=request.include_code,
            custom_title=request.title
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate LaTeX report: {str(e)}"
        )


@router.post("/export", response_model=ExportResponse)
async def export_report(request: ExportRequest):
    """
    Generate a report for the EDA results in the specified format.
    
    If uid and csv_id are provided:
    - PDF: Uploads directly to Cloudinary and returns download URL
    - Markdown/LaTeX: Creates a ZIP with the report + images, uploads to Cloudinary
    
    If uid/csv_id not provided, falls back to local file generation only.
    
    Args:
        request: Export configuration including dataset name, format, and what to include
    
    Returns:
        ExportResponse with download_url (Cloudinary) and export_id (MongoDB)
    """
    # Check if there's data to export
    status = check_export_status(request.dataset_name)
    
    if not status.can_export:
        raise HTTPException(
            status_code=404,
            detail=f"No exportable data found for dataset: {request.dataset_name}"
        )
    
    try:
        # Use cloud-enabled functions if user context provided
        use_cloud = request.uid and request.csv_id
        
        if request.format == "markdown":
            if use_cloud:
                result = await generate_markdown_report_with_upload(
                    dataset_name=request.dataset_name,
                    uid=request.uid,
                    csv_id=request.csv_id,
                    include_summary=request.include_summary,
                    include_plots=request.include_plots,
                    include_vlm_analysis=request.include_vlm_analysis,
                    include_code=request.include_code,
                    custom_title=request.title
                )
            else:
                result = generate_markdown_report(
                    dataset_name=request.dataset_name,
                    include_summary=request.include_summary,
                    include_plots=request.include_plots,
                    include_vlm_analysis=request.include_vlm_analysis,
                    include_code=request.include_code,
                    custom_title=request.title
                )
        elif request.format == "latex":
            if use_cloud:
                result = await generate_latex_report_with_upload(
                    dataset_name=request.dataset_name,
                    uid=request.uid,
                    csv_id=request.csv_id,
                    include_summary=request.include_summary,
                    include_plots=request.include_plots,
                    include_vlm_analysis=request.include_vlm_analysis,
                    include_code=request.include_code,
                    custom_title=request.title
                )
            else:
                result = generate_latex_report(
                    dataset_name=request.dataset_name,
                    include_summary=request.include_summary,
                    include_plots=request.include_plots,
                    include_vlm_analysis=request.include_vlm_analysis,
                    include_code=request.include_code,
                    custom_title=request.title
                )
        else:  # pdf
            if use_cloud:
                result = await generate_pdf_report_with_upload(
                    dataset_name=request.dataset_name,
                    uid=request.uid,
                    csv_id=request.csv_id,
                    include_summary=request.include_summary,
                    include_plots=request.include_plots,
                    include_vlm_analysis=request.include_vlm_analysis,
                    include_code=request.include_code,
                    custom_title=request.title
                )
            else:
                result = generate_pdf_report(
                    dataset_name=request.dataset_name,
                    include_summary=request.include_summary,
                    include_plots=request.include_plots,
                    include_vlm_analysis=request.include_vlm_analysis,
                    include_code=request.include_code,
                    custom_title=request.title
                )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate report: {str(e)}"
        )


@router.get("/export/download/{dataset_name}")
async def download_latest_export(dataset_name: str):
    """
    Download the latest generated PDF report for a dataset.
    
    Args:
        dataset_name: Name of the dataset
    
    Returns:
        PDF file download
    """
    paths = get_dataset_paths(dataset_name)
    export_dir = paths["export_dir"]
    
    if not os.path.exists(export_dir):
        raise HTTPException(
            status_code=404,
            detail=f"No exports found for dataset: {dataset_name}"
        )
    
    # Find the latest PDF for this dataset
    pdf_files = [
        f for f in os.listdir(export_dir)
        if f.startswith(dataset_name) and f.endswith('.pdf')
    ]
    
    if not pdf_files:
        raise HTTPException(
            status_code=404,
            detail=f"No PDF exports found for dataset: {dataset_name}"
        )
    
    # Get the most recent file
    latest_pdf = sorted(pdf_files)[-1]
    pdf_path = os.path.join(export_dir, latest_pdf)
    
    return FileResponse(
        path=pdf_path,
        filename=latest_pdf,
        media_type="application/pdf"
    )


@router.get("/export/download/{dataset_name}/markdown")
async def download_latest_markdown_export(dataset_name: str):
    """
    Download the latest generated Markdown report for a dataset.
    
    Args:
        dataset_name: Name of the dataset
    
    Returns:
        Markdown file download
    """
    paths = get_dataset_paths(dataset_name)
    export_dir = paths["export_dir"]
    
    if not os.path.exists(export_dir):
        raise HTTPException(
            status_code=404,
            detail=f"No exports found for dataset: {dataset_name}"
        )
    
    # Find the latest Markdown file for this dataset
    md_files = [
        f for f in os.listdir(export_dir)
        if f.startswith(dataset_name) and f.endswith('.md')
    ]
    
    if not md_files:
        raise HTTPException(
            status_code=404,
            detail=f"No Markdown exports found for dataset: {dataset_name}"
        )
    
    # Get the most recent file
    latest_md = sorted(md_files)[-1]
    md_path = os.path.join(export_dir, latest_md)
    
    return FileResponse(
        path=md_path,
        filename=latest_md,
        media_type="text/markdown"
    )


@router.get("/export/download/{dataset_name}/latex")
async def download_latest_latex_export(dataset_name: str):
    """
    Download the latest generated LaTeX report for a dataset.
    
    Args:
        dataset_name: Name of the dataset
    
    Returns:
        LaTeX (.tex) file download
    """
    paths = get_dataset_paths(dataset_name)
    export_dir = paths["export_dir"]
    
    if not os.path.exists(export_dir):
        raise HTTPException(
            status_code=404,
            detail=f"No exports found for dataset: {dataset_name}"
        )
    
    # Find the latest LaTeX file for this dataset
    tex_files = [
        f for f in os.listdir(export_dir)
        if f.startswith(dataset_name) and f.endswith('.tex')
    ]
    
    if not tex_files:
        raise HTTPException(
            status_code=404,
            detail=f"No LaTeX exports found for dataset: {dataset_name}"
        )
    
    # Get the most recent file
    latest_tex = sorted(tex_files)[-1]
    tex_path = os.path.join(export_dir, latest_tex)
    
    return FileResponse(
        path=tex_path,
        filename=latest_tex,
        media_type="application/x-latex"
    )


@router.get("/export/list/{dataset_name}")
async def list_exports(dataset_name: str):
    """
    List all available exports for a dataset.
    
    Args:
        dataset_name: Name of the dataset
    
    Returns:
        List of available export files (PDFs, Markdown, and LaTeX)
    """
    paths = get_dataset_paths(dataset_name)
    export_dir = paths["export_dir"]
    
    if not os.path.exists(export_dir):
        return {
            "dataset_name": dataset_name,
            "exports": {"pdf": [], "markdown": [], "latex": []},
            "total": 0
        }
    
    # Find all PDFs for this dataset
    pdf_files = [
        f for f in os.listdir(export_dir)
        if f.startswith(dataset_name) and f.endswith('.pdf')
    ]
    
    # Find all Markdown files for this dataset
    md_files = [
        f for f in os.listdir(export_dir)
        if f.startswith(dataset_name) and f.endswith('.md')
    ]
    
    # Find all LaTeX files for this dataset
    tex_files = [
        f for f in os.listdir(export_dir)
        if f.startswith(dataset_name) and f.endswith('.tex')
    ]
    
    pdf_exports = []
    for pdf_file in sorted(pdf_files, reverse=True):
        pdf_path = os.path.join(export_dir, pdf_file)
        pdf_exports.append({
            "filename": pdf_file,
            "path": pdf_path,
            "size_bytes": os.path.getsize(pdf_path),
            "format": "pdf"
        })
    
    md_exports = []
    for md_file in sorted(md_files, reverse=True):
        md_path = os.path.join(export_dir, md_file)
        md_exports.append({
            "filename": md_file,
            "path": md_path,
            "size_bytes": os.path.getsize(md_path),
            "format": "markdown"
        })
    
    tex_exports = []
    for tex_file in sorted(tex_files, reverse=True):
        tex_path = os.path.join(export_dir, tex_file)
        tex_exports.append({
            "filename": tex_file,
            "path": tex_path,
            "size_bytes": os.path.getsize(tex_path),
            "format": "latex"
        })
    
    return {
        "dataset_name": dataset_name,
        "exports": {
            "pdf": pdf_exports,
            "markdown": md_exports,
            "latex": tex_exports
        },
        "total": len(pdf_exports) + len(md_exports) + len(tex_exports)
    }


# ---------------- Cloud Storage Endpoints ----------------

@router.get("/export/history/{uid}")
async def get_export_history(
    uid: str,
    dataset_name: Optional[str] = Query(None, description="Filter by dataset name"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of results")
):
    """
    Get export history for a user from MongoDB.
    
    Args:
        uid: User ID
        dataset_name: Optional filter by dataset
        limit: Maximum number of results (default 20, max 100)
    
    Returns:
        List of past exports with download URLs
    """
    exports = get_user_exports(uid, dataset_name, limit)
    
    return {
        "uid": uid,
        "dataset_name": dataset_name,
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


@router.post("/export/regenerate-url/{export_id}")
async def regenerate_download_url(export_id: str):
    """
    Regenerate a signed Cloudinary URL for an export.
    Use this when the original URL has expired (7-day expiration).
    
    Args:
        export_id: MongoDB ObjectId as string
    
    Returns:
        New signed download URL
    """
    new_url = regenerate_export_url(export_id)
    
    if not new_url:
        raise HTTPException(
            status_code=404,
            detail=f"Could not regenerate URL for export: {export_id}. Export not found or has no Cloudinary public_id."
        )
    
    return {
        "export_id": export_id,
        "download_url": new_url,
        "message": "URL regenerated successfully. Valid for 7 days."
    }
