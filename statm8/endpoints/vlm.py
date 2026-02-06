from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from statm8.models.vlm import AnalyzePlotsRequest, AnalyzePlotsResponse, StreamPlotAnalysisResponse
from statm8.services.vlm import (
    analyze_plots_sync,
    analyze_plots_stream,
    get_plot_dir_from_dataset,
    get_plots_in_directory
)
import os

router = APIRouter(tags=["VLM Analysis"])


@router.post("/analyze-plots-stream")
async def analyze_plots_streaming(request: AnalyzePlotsRequest):
    """
    Analyze all plots in a dataset's output directory using Vision Language Model.
    Streams analysis for each plot as it's processed.
    
    Args:
        request: Contains dataset_name and optional custom plot_dir
    
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
            for result in analyze_plots_stream(request.dataset_name, plot_dir):
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
    
    Args:
        request: Contains dataset_name and optional custom plot_dir
    
    Returns:
        Complete analysis of all plots with individual insights and a summary
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
        result = analyze_plots_sync(request.dataset_name, plot_dir)
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
