from pydantic import BaseModel
from typing import List, Optional

class CodeBlock(BaseModel):
    """Represents a single executable code block"""
    id: int
    description: str
    code: str
    status: str = "pending"  # pending, executing, success, error
    output: Optional[str] = None
    error: Optional[str] = None
    execution_time: Optional[float] = None
    plots_generated: List[str] = []
    plot_urls: List[str] = []  # Cloudinary URLs for generated plots


class GenerateEDARequest(BaseModel):
    """Request model for EDA generation"""
    uid: str  # User ID (required)
    csv_id: str  # CSV file ID (required) - csv_name will be fetched from this
    comments: Optional[str] = None  # User comments/instructions for EDA generation


class GenerateEDAResponse(BaseModel):
    """Response model for EDA generation"""
    csv_id: str  # CSV file ID
    csv_name: str  # Display name for the CSV
    total_blocks: int
    blocks: List[CodeBlock]
    overall_status: str  # generating, executing, completed, failed
    plot_urls: List[str] = []  # All Cloudinary URLs for generated plots
    

class StreamCodeBlockResponse(BaseModel):
    """Streaming response for individual code blocks"""
    block_id: int
    description: str
    code: str
    status: str
    output: Optional[str] = None
    error: Optional[str] = None
    plots_generated: List[str] = []
    plot_urls: List[str] = []  # Cloudinary URLs for generated plots