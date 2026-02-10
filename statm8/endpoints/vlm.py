from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from statm8.models.vlm import AnalyzePlotsRequest, AnalyzePlotsResponse, StreamPlotAnalysisResponse
from statm8.services.vlm import (
    analyze_plots_sync,
    analyze_plots_stream
)
from statm8.services.storage import (
    get_vlm_analysis_from_db,
    get_vlm_analysis_by_csv,
    get_plots_for_csv,
    get_csv_name_by_id
)

router = APIRouter(tags=["VLM Analysis"])


@router.post("/analyze-plots-stream")
async def analyze_plots_streaming(request: AnalyzePlotsRequest):
    """
    Analyze all plots for a CSV file using Vision Language Model.
    Fetches plots from MongoDB/Cloudinary and streams analysis for each.
    
    Note: Streaming mode does not support caching - use /analyze-plots for cached responses.
    
    Args:
        request: Contains uid, csv_id, and comment_id
    
    Returns:
        Server-Sent Events stream with analysis for each plot, followed by a summary
    """
    # Check if plots exist in MongoDB
    plots = get_plots_for_csv(request.csv_id, request.uid, request.comment_id)
    if not plots:
        csv_name = get_csv_name_by_id(request.csv_id)
        raise HTTPException(
            status_code=404,
            detail=f"No plots found for CSV: {csv_name}. Run EDA generation first."
        )
    
    async def event_stream():
        try:
            async for result in analyze_plots_stream(
                uid=request.uid,
                csv_id=request.csv_id,
                comment_id=request.comment_id
            ):
                data = result.model_dump_json()
                yield f"data: {data}\n\n"
        except Exception as e:
            error_response = StreamPlotAnalysisResponse(
                plot_index=-1,
                total_plots=0,
                plot_filename="error",
                plot_url="",
                analysis="",
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


@router.post("/analyze-plots", response_model=AnalyzePlotsResponse)
async def analyze_plots(request: AnalyzePlotsRequest):
    """
    Analyze all plots for a CSV file using Vision Language Model.
    Fetches plots from MongoDB/Cloudinary and returns complete analysis.
    
    Supports caching: If uid, csv_id, and comment_id are provided and use_cache=True,
    returns cached analysis if available. This saves API costs for repeated analyses.
    
    Args:
        request: Contains uid, csv_id, comment_id, and use_cache flag
    
    Returns:
        Complete analysis of all plots with individual insights and a summary.
        Response includes 'cached' field indicating if result was from cache.
    """
    # Check if plots exist in MongoDB
    plots = get_plots_for_csv(request.csv_id, request.uid, request.comment_id)
    if not plots:
        csv_name = get_csv_name_by_id(request.csv_id)
        raise HTTPException(
            status_code=404,
            detail=f"No plots found for CSV: {csv_name}. Run EDA generation first."
        )
    
    try:
        result = await analyze_plots_sync(
            uid=request.uid,
            csv_id=request.csv_id,
            comment_id=request.comment_id,
            use_cache=request.use_cache
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze plots: {str(e)}"
        )


@router.get("/plots/{csv_id}")
async def list_csv_plots(
    csv_id: str,
    uid: Optional[str] = Query(None, description="User ID for filtering")
):
    """
    List all available plots for a given CSV file from MongoDB.
    
    Args:
        csv_id: MongoDB ObjectId string for the CSV file
        uid: Optional user ID for filtering
    
    Returns:
        List of plot filenames and their Cloudinary URLs
    """
    plots = get_plots_for_csv(csv_id, uid)
    csv_name = get_csv_name_by_id(csv_id)
    
    if not plots:
        raise HTTPException(
            status_code=404,
            detail=f"No plots found for CSV: {csv_name}"
        )
    
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


# ---------------- VLM Analysis Retrieval Endpoints ----------------

@router.get("/vlm-analysis/{csv_id}")
async def get_vlm_analysis(
    csv_id: str,
    uid: Optional[str] = Query(None, description="User ID for user-specific analysis"),
    comment_id: Optional[str] = Query(None, description="Comment ID for specific analysis")
):
    """
    Retrieve stored VLM analysis for a CSV file from MongoDB.
    
    Args:
        csv_id: MongoDB ObjectId string for the CSV file
        uid: Optional user ID for user-specific results
        comment_id: Optional comment ID for specific analysis
    
    Returns:
        Stored VLM analysis if available
    """
    csv_name = get_csv_name_by_id(csv_id)
    
    # Try MongoDB with user context if provided
    if uid and comment_id:
        analysis = get_vlm_analysis_from_db(uid, csv_id, comment_id)
        if analysis:
            return {
                "source": "mongodb",
                "csv_id": csv_id,
                "csv_name": csv_name,
                "analysis": analysis
            }
    
    # Try MongoDB without user context (latest for CSV)
    analysis = get_vlm_analysis_by_csv(csv_id)
    if analysis:
        return {
            "source": "mongodb",
            "csv_id": csv_id,
            "csv_name": csv_name,
            "analysis": analysis
        }
    
    raise HTTPException(
        status_code=404,
        detail=f"No VLM analysis found for CSV: {csv_name}. Run /analyze-plots first."
    )
