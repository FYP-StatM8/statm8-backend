from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from statm8.models.export import ExportRequest, ExportResponse, ExportStatusResponse
from statm8.services.export import (
    generate_pdf_report,
    check_export_status,
    get_dataset_paths
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


@router.get("/export/list/{dataset_name}")
async def list_exports(dataset_name: str):
    """
    List all available exports for a dataset.
    
    Args:
        dataset_name: Name of the dataset
    
    Returns:
        List of available export files
    """
    paths = get_dataset_paths(dataset_name)
    export_dir = paths["export_dir"]
    
    if not os.path.exists(export_dir):
        return {
            "dataset_name": dataset_name,
            "exports": [],
            "total": 0
        }
    
    # Find all PDFs for this dataset
    pdf_files = [
        f for f in os.listdir(export_dir)
        if f.startswith(dataset_name) and f.endswith('.pdf')
    ]
    
    exports = []
    for pdf_file in sorted(pdf_files, reverse=True):
        pdf_path = os.path.join(export_dir, pdf_file)
        exports.append({
            "filename": pdf_file,
            "path": pdf_path,
            "size_bytes": os.path.getsize(pdf_path)
        })
    
    return {
        "dataset_name": dataset_name,
        "exports": exports,
        "total": len(exports)
    }
