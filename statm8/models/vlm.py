from pydantic import BaseModel
from typing import List, Optional


class PlotAnalysis(BaseModel):
    """Analysis result for a single plot"""
    plot_filename: str
    plot_path: str
    analysis: str
    plot_type: Optional[str] = None
    status: str = "pending"  # pending, analyzing, success, error
    error: Optional[str] = None


class AnalyzePlotsRequest(BaseModel):
    """Request model for VLM plot analysis"""
    dataset_name: str  # Name of dataset (e.g., 'iris', 'breast-cancer')
    plot_dir: Optional[str] = None  # Optional custom plot directory path
    # User context for MongoDB persistence/caching
    uid: Optional[str] = None  # User ID
    csv_id: Optional[str] = None  # CSV file ID
    use_cache: bool = True  # Whether to use cached analysis if available


class AnalyzePlotsResponse(BaseModel):
    """Response model for VLM plot analysis"""
    dataset_name: str
    plot_dir: str
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
    plot_path: str
    analysis: str
    status: str
    error: Optional[str] = None
    is_summary: bool = False  # True when this is the final summary
