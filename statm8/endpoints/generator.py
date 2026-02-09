from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from statm8.models.generator import GenerateEDARequest, GenerateEDAResponse, StreamCodeBlockResponse
from statm8.services.generator import (
    generate_and_execute_eda, 
    generate_and_execute_eda_sync, 
    get_output_dir_from_filepath,
    generate_and_execute_eda_with_upload,
    generate_and_execute_eda_sync_with_upload
)
import tempfile
import os
from pathlib import Path
import io
from typing import Optional
from statm8.services.storage import (
    add_csv_comment, 
    add_comment_assets, 
    get_csv_file_for_processing,
    get_plots_for_csv,
    get_csv_name_by_id
)

router = APIRouter(tags=["EDA Generator"])


async def get_csv_temp_file(csv_id: str) -> tuple[str, str]:
    """
    Fetch CSV from Cloudinary by csv_id and save to a temp file.
    Returns (temp_file_path, csv_name).
    """
    csv_bytes, csv_name = await get_csv_file_for_processing(csv_id)
    
    # Create temp file
    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, f"{csv_name}.csv")
    
    with open(temp_path, 'wb') as f:
        f.write(csv_bytes)
    
    return temp_path, csv_name


@router.post("/generate-eda-stream")
async def generate_eda_stream(request: GenerateEDARequest, max_retries: int = 2):
    """
    Generate and execute EDA code blocks for a CSV file with streaming response.
    Fetches CSV from Cloudinary and uploads generated plots immediately.
    
    Args:
        request: Contains uid, csv_id and optional comments
        max_retries: Maximum number of regeneration attempts if code fails (default: 2)
    """
    # Fetch CSV from Cloudinary to temp file
    try:
        temp_file_path, csv_name = await get_csv_temp_file(request.csv_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Could not fetch CSV: {str(e)}")
    
    output_dir = get_output_dir_from_filepath(temp_file_path)

    # Add CSV comment
    final_comment = request.comments.strip() if request.comments and request.comments.strip() else "EMPTY COMMENT"
    comment_result = add_csv_comment(
        uid=request.uid,
        csv_id=request.csv_id,
        comment=final_comment
    )
    comment_id = comment_result["comment_id"]
    
    async def event_stream():
        try:
            # Use the new upload-enabled generator
            async for result in generate_and_execute_eda_with_upload(
                temp_file_path, 
                output_dir, 
                request.comments, 
                max_retries,
                request.uid,
                request.csv_id
            ):
                data = result.model_dump()
                
                # Store successful blocks with assets
                if data.get("status") == "success":
                    images: list[UploadFile] = []
                    
                    # If plots were uploaded, they're now URLs - we can skip local file reading
                    # The images are already in Cloudinary
                    
                    await add_comment_assets(
                        comment_id=comment_id,
                        code=data.get("code", ""),
                        description=data.get("description", ""),
                        images=images  # Empty since plots are in Cloudinary
                    )

                yield f"data: {result.model_dump_json()}\n\n"
                
        except Exception as e:
            error_response = StreamCodeBlockResponse(
                block_id=-1,
                description="Error occurred",
                code="",
                status="error",
                error=str(e)
            )
            yield f"data: {error_response.model_dump_json()}\n\n"
        finally:
            # Cleanup temp file
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
    
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
    Generate and execute EDA code blocks for a CSV file.
    Fetches CSV from Cloudinary and uploads generated plots immediately.
    
    Args:
        request: Contains uid, csv_id and optional comments
        max_retries: Maximum number of regeneration attempts if code fails (default: 2)
    """
    # Fetch CSV from Cloudinary to temp file
    try:
        temp_file_path, csv_name = await get_csv_temp_file(request.csv_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Could not fetch CSV: {str(e)}")
    
    output_dir = get_output_dir_from_filepath(temp_file_path)
    
    try:
        result = await generate_and_execute_eda_sync_with_upload(
            temp_file_path, 
            output_dir, 
            request.comments, 
            max_retries,
            request.uid,
            request.csv_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating EDA: {str(e)}")
    finally:
        # Cleanup temp file
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)


@router.get("/list-plots/{csv_id}")
async def list_plots(csv_id: str, uid: Optional[str] = None):
    """
    List all generated plots for a CSV file from MongoDB.
    """
    csv_name = get_csv_name_by_id(csv_id)
    plots = get_plots_for_csv(csv_id, uid)
    
    return {
        "csv_id": csv_id,
        "csv_name": csv_name,
        "total_plots": len(plots),
        "plots": [
            {
                "filename": p["filename"],
                "url": p["cloudinary_url"],
                "created_at": p.get("created_at")
            }
            for p in plots
        ]
    }