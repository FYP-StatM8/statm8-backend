from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from statm8.models.generator import GenerateEDARequest, GenerateEDAResponse, StreamCodeBlockResponse
from statm8.services.generator import generate_and_execute_eda, generate_and_execute_eda_sync, get_output_dir_from_filepath
import json
import os

router = APIRouter(tags=["EDA Generator"])


@router.post("/generate-eda-stream")
async def generate_eda_stream(request: GenerateEDARequest, max_retries: int = 2):
    """
    Generate and execute EDA code blocks for a CSV file with streaming response
    
    This endpoint streams each code block as it's generated and executed, providing
    real-time feedback on the EDA process.
    
    Args:
        request: Contains file_path and optional comments
        max_retries: Maximum number of regeneration attempts if code fails (default: 2)
    """
    if not os.path.exists(request.file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {request.file_path}")
    
    if not request.file_path.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")
    
    output_dir = get_output_dir_from_filepath(request.file_path)
    
    async def event_stream():
        try:
            for result in generate_and_execute_eda(request.file_path, output_dir, request.comments, max_retries):
                data = result.model_dump_json()
                yield f"data: {data}\n\n"
        except Exception as e:
            error_response = StreamCodeBlockResponse(
                block_id=-1,
                description="Error occurred",
                code="",
                status="error",
                error=str(e)
            )
            yield f"data: {error_response.model_dump_json()}\n\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/generate-eda", response_model=GenerateEDAResponse)
async def generate_eda(request: GenerateEDARequest, max_retries: int = 2):
    """
    Generate and execute EDA code blocks for a CSV file
    
    This endpoint generates all code blocks, executes them, and returns
    the complete results in a single response.
    
    Args:
        request: Contains file_path and optional comments
        max_retries: Maximum number of regeneration attempts if code fails (default: 2)
    """
    if not os.path.exists(request.file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {request.file_path}")
    
    if not request.file_path.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")
    
    output_dir = get_output_dir_from_filepath(request.file_path)
    
    try:
        result = generate_and_execute_eda_sync(request.file_path, output_dir, request.comments, max_retries)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating EDA: {str(e)}")


@router.get("/list-plots")
async def list_plots(output_dir: str = "outputs/plots"):
    """
    List all generated plots in the output directory
    """
    if not os.path.exists(output_dir):
        return {"plots": [], "message": "Output directory does not exist"}
    
    plots = [f for f in os.listdir(output_dir) if f.endswith(('.png', '.jpg', '.jpeg', '.svg'))]
    
    return {
        "output_dir": output_dir,
        "total_plots": len(plots),
        "plots": plots
    }