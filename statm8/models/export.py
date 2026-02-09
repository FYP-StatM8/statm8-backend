from pydantic import BaseModel
from typing import List, Optional, Literal
from datetime import datetime


class PlotInfo(BaseModel):
    """Information about a plot included in the export"""
    filename: str
    url: str = ""  # Cloudinary URL
    analysis: Optional[str] = None  # VLM-generated analysis if available


class ExportSection(BaseModel):
    """A section of the export report"""
    title: str
    content: str
    section_type: str = "text"  # text, table, plots


class ExportRequest(BaseModel):
    """Request model for report export"""
    uid: str  # User ID (required)
    csv_id: str  # CSV file ID (required)
    vlm_analysis_id: Optional[str] = None  # VLM analysis ID (required if include_vlm_analysis=True)
    include_summary: bool = True  # Include dataset summary
    include_plots: bool = True  # Include generated plots
    include_vlm_analysis: bool = False  # Include VLM plot analyses (requires vlm_analysis_id)
    include_code: bool = False  # Include generated code blocks
    title: Optional[str] = None  # Custom report title
    format: Literal["pdf", "markdown", "latex"] = "pdf"  # Export format: pdf, markdown or latex


class ExportResponse(BaseModel):
    """Response model for PDF export"""
    csv_id: str  # CSV file ID
    csv_name: str  # Display name for the CSV
    file_size_bytes: int
    sections_included: List[str]
    total_plots: int
    generated_at: str
    status: str  # success, failed
    # Cloud storage fields
    download_url: str  # Cloudinary URL for direct download
    export_id: str  # MongoDB export ID
    format: Literal["pdf", "markdown", "latex"] = "pdf"
    is_zip: bool = False  # True for markdown/latex exports (bundled with images)


class ExportStatusResponse(BaseModel):
    """Response model for checking what can be exported"""
    csv_id: str  # CSV file ID
    csv_name: str  # Display name for the CSV
    has_summary: bool
    has_plots: bool
    plot_count: int
    has_vlm_analysis: bool
    can_export: bool
