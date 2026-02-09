from pydantic import BaseModel
from typing import List, Optional


class PlotAnalysis(BaseModel):
    """Analysis result for a single plot"""
    plot_filename: str
    plot_url: str = ""  # Cloudinary URL
    analysis: str
    plot_type: Optional[str] = None
    status: str = "pending"  # pending, analyzing, success, error
    error: Optional[str] = None


class AnalyzePlotsRequest(BaseModel):
    """Request model for VLM plot analysis"""
    uid: str  # User ID (required)
    csv_id: str  # CSV file ID (required)
    comment_id: str  # Comment ID (required) - VLM analysis is per-comment
    use_cache: bool = True  # Whether to use cached analysis if available


class AnalyzePlotsResponse(BaseModel):
    """Response model for VLM plot analysis"""
    csv_id: str  # CSV file ID
    csv_name: str  # Display name for the CSV
    comment_id: str  # Comment ID this analysis is for
    total_plots: int
    plot_analyses: List[PlotAnalysis]
    summary: Optional[str] = None
    overall_status: str  # analyzing, completed, failed
    cached: bool = False  # True if response was loaded from cache


class StreamPlotAnalysisResponse(BaseModel):
    """Streaming response for individual plot analysis"""
    plot_index: int
    total_plots: int
    plot_filename: str
    plot_url: str = ""  # Cloudinary URL
    analysis: str
    status: str
    error: Optional[str] = None
    is_summary: bool = False  # True when this is the final summary
