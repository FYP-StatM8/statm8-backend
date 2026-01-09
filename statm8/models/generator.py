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


class GenerateEDARequest(BaseModel):
    """Request model for EDA generation"""
    file_path: str
    comments: Optional[str] = None  # User comments/instructions for EDA generation
    uid: str
    csv_id: str


class GenerateEDAResponse(BaseModel):
    """Response model for EDA generation"""
    file_path: str
    output_dir: str
    total_blocks: int
    blocks: List[CodeBlock]
    overall_status: str  # generating, executing, completed, failed
    

class StreamCodeBlockResponse(BaseModel):
    """Streaming response for individual code blocks"""
    block_id: int
    description: str
    code: str
    status: str
    output: Optional[str] = None
    error: Optional[str] = None
    plots_generated: List[str] = []