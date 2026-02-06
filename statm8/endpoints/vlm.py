from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from statm8.models.vlm import AnalyzePlotsRequest, AnalyzePlotsResponse, StreamPlotAnalysisResponse
from statm8.services.vlm import (
    analyze_plots_sync,
    analyze_plots_stream,
    get_plot_dir_from_dataset,
    get_plots_in_directory
)
from statm8.services.storage import (
    get_vlm_analysis_from_db,
    get_vlm_analysis_by_dataset
)
import os

router = APIRouter(tags=["VLM Analysis"])


@router.post("/analyze-plots-stream")
async def analyze_plots_streaming(request: AnalyzePlotsRequest):
    """
    Analyze all plots in a dataset's output directory using Vision Language Model.
    Streams analysis for each plot as it's processed.
    
    Note: Streaming mode does not support caching - use /analyze-plots for cached responses.
    
    Args:
        request: Contains dataset_name, optional plot_dir, and user context (uid, csv_id)
    
    Returns:
        Server-Sent Events stream with analysis for each plot, followed by a summary
    """
    plot_dir = request.plot_dir or get_plot_dir_from_dataset(request.dataset_name)
    
    if not os.path.exists(plot_dir):
        raise HTTPException(
            status_code=404,
            detail=f"Plot directory not found: {plot_dir}. Run EDA generation first."
        )
    
    plots = get_plots_in_directory(plot_dir)
    if not plots:
        raise HTTPException(
            status_code=404,
            detail=f"No plot files found in: {plot_dir}"
        )
    
    async def event_stream():
        try:
            for result in analyze_plots_stream(
                request.dataset_name,
                plot_dir,
                uid=request.uid,
                csv_id=request.csv_id
            ):
                data = result.model_dump_json()
                yield f"data: {data}\n\n"
        except Exception as e:
            error_response = StreamPlotAnalysisResponse(
                plot_index=-1,
                total_plots=0,
                plot_filename="error",
                plot_path="",
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
    Analyze all plots in a dataset's output directory using Vision Language Model.
    Returns complete analysis in a single response.
    
    Supports caching: If uid and csv_id are provided and use_cache=True,
    returns cached analysis if plots haven't changed (based on file hash).
    This saves Groq API costs for repeated analyses.
    
    Args:
        request: Contains dataset_name, optional plot_dir, user context (uid, csv_id), and use_cache flag
    
    Returns:
        Complete analysis of all plots with individual insights and a summary.
        Response includes 'cached' field indicating if result was from cache.
    """
    plot_dir = request.plot_dir or get_plot_dir_from_dataset(request.dataset_name)
    
    if not os.path.exists(plot_dir):
        raise HTTPException(
            status_code=404,
            detail=f"Plot directory not found: {plot_dir}. Run EDA generation first."
        )
    
    plots = get_plots_in_directory(plot_dir)
    if not plots:
        raise HTTPException(
            status_code=404,
            detail=f"No plot files found in: {plot_dir}"
        )
    
    try:
        result = analyze_plots_sync(
            request.dataset_name,
            plot_dir,
            uid=request.uid,
            csv_id=request.csv_id,
            use_cache=request.use_cache
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze plots: {str(e)}"
        )


@router.get("/plots/{dataset_name}")
async def list_dataset_plots(dataset_name: str):
    """
    List all available plots for a given dataset.
    
    Args:
        dataset_name: Name of the dataset (e.g., 'iris', 'breast-cancer')
    
    Returns:
        List of plot filenames and their paths
    """
    plot_dir = get_plot_dir_from_dataset(dataset_name)
    
    if not os.path.exists(plot_dir):
        raise HTTPException(
            status_code=404,
            detail=f"Plot directory not found: {plot_dir}"
        )
    
    plots = get_plots_in_directory(plot_dir)
    
    return {
        "dataset_name": dataset_name,
        "plot_dir": plot_dir,
        "total_plots": len(plots),
        "plots": [
            {
                "filename": plot,
                "path": os.path.join(plot_dir, plot)
            }
            for plot in plots
        ]
    }


# ---------------- VLM Analysis Retrieval Endpoints ----------------

@router.get("/vlm-analysis/{dataset_name}")
async def get_vlm_analysis(
    dataset_name: str,
    uid: Optional[str] = Query(None, description="User ID for user-specific analysis"),
    csv_id: Optional[str] = Query(None, description="CSV file ID")
):
    """
    Retrieve stored VLM analysis for a dataset.
    
    If uid and csv_id are provided, returns user-specific analysis from MongoDB.
    Otherwise, returns the latest analysis for the dataset.
    Also checks local JSON file as fallback.
    
    Args:
        dataset_name: Name of the dataset
        uid: Optional user ID for user-specific results
        csv_id: Optional CSV file ID
    
    Returns:
        Stored VLM analysis if available
    """
    # Try MongoDB first if user context provided
    if uid and csv_id:
        plot_dir = get_plot_dir_from_dataset(dataset_name)
        analysis = get_vlm_analysis_from_db(uid, csv_id, dataset_name, plot_dir)
        if analysis:
            return {
                "source": "mongodb",
                "dataset_name": dataset_name,
                "analysis": analysis
            }
    
    # Try MongoDB without user context (latest for dataset)
    analysis = get_vlm_analysis_by_dataset(dataset_name)
    if analysis:
        return {
            "source": "mongodb",
            "dataset_name": dataset_name,
            "analysis": analysis
        }
    
    # Fallback to local JSON file
    from statm8.services.export import get_dataset_paths, load_vlm_analysis
    paths = get_dataset_paths(dataset_name)
    local_analysis = load_vlm_analysis(paths["vlm_analysis"])
    
    if local_analysis:
        return {
            "source": "local_file",
            "dataset_name": dataset_name,
            "analysis": local_analysis
        }
    
    raise HTTPException(
        status_code=404,
        detail=f"No VLM analysis found for dataset: {dataset_name}. Run /analyze-plots first."
    )
