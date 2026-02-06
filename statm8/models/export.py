from pydantic import BaseModel
from typing import List, Optional, Literal
from datetime import datetime


class PlotInfo(BaseModel):
    """Information about a plot included in the export"""
    filename: str
    path: str
    analysis: Optional[str] = None  # VLM-generated analysis if available


class ExportSection(BaseModel):
    """A section of the export report"""
    title: str
    content: str
    section_type: str = "text"  # text, table, plots


class ExportRequest(BaseModel):
    """Request model for report export"""
    dataset_name: str
    include_summary: bool = True  # Include dataset summary
    include_plots: bool = True  # Include generated plots
    include_vlm_analysis: bool = False  # Include VLM plot analyses (requires prior VLM run)
    include_code: bool = False  # Include generated code blocks
    title: Optional[str] = None  # Custom report title
    format: Literal["pdf", "markdown", "latex"] = "pdf"  # Export format: pdf, markdown or latex
    # User context for cloud storage (optional - falls back to local-only if not provided)
    uid: Optional[str] = None  # User ID
    csv_id: Optional[str] = None  # CSV file ID


class ExportResponse(BaseModel):
    """Response model for PDF export"""
    dataset_name: str
    export_path: str
    file_size_bytes: int
    sections_included: List[str]
    total_plots: int
    generated_at: str
    status: str  # success, failed
    # Cloud storage fields
    download_url: Optional[str] = None  # Cloudinary URL for direct download
    export_id: Optional[str] = None  # MongoDB export ID
    format: Literal["pdf", "markdown", "latex"] = "pdf"
    is_zip: bool = False  # True for markdown/latex exports (bundled with images)


class ExportStatusResponse(BaseModel):
    """Response model for checking what can be exported"""
    dataset_name: str
    has_summary: bool
    summary_path: Optional[str] = None
    has_plots: bool
    plot_count: int
    plot_dir: Optional[str] = None
    has_vlm_analysis: bool
    vlm_analysis_path: Optional[str] = None
    can_export: bool
