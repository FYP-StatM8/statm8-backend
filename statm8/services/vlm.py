import base64
import asyncio
import httpx
from typing import List, Generator, Optional, Dict, Any
from langchain_groq import ChatGroq
from statm8.constants.stat import GROQ_API_KEY
from statm8.constants.vlm import VLM_MODEL, PLOT_ANALYSIS_TEMPLATE, SUMMARY_TEMPLATE
from statm8.models.vlm import PlotAnalysis, AnalyzePlotsResponse, StreamPlotAnalysisResponse
from statm8.services.storage import (
    save_vlm_analysis_to_db,
    get_vlm_analysis_from_db,
    get_vlm_analysis_by_csv,
    get_plots_for_csv,
    get_csv_name_by_id,
    compute_plots_hash
)


def get_vlm():
    """Get VLM instance for vision analysis"""
    return ChatGroq(
        model=VLM_MODEL,
        temperature=0.3,
        max_retries=2,
        api_key=GROQ_API_KEY
    )


def get_plots_from_mongodb(csv_id: str, uid: Optional[str] = None, comment_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get plot information from MongoDB.
    
    Args:
        csv_id: MongoDB ObjectId string for the CSV file
        uid: Optional user ID filter
        comment_id: Optional comment ID filter (required for VLM analysis endpoints)
    
    Returns:
        List of plot documents with cloudinary URLs
    """
    return get_plots_for_csv(csv_id, uid, comment_id)


async def fetch_image_bytes(url: str) -> bytes:
    """Fetch image bytes from Cloudinary URL"""
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content


def encode_image_bytes_to_base64(image_bytes: bytes) -> str:
    """Encode image bytes to base64 string"""
    return base64.b64encode(image_bytes).decode("utf-8")


async def analyze_single_plot_from_url(
    vlm: ChatGroq,
    image_url: str,
    plot_filename: str,
    csv_name: str
) -> str:
    """Analyze a single plot image from Cloudinary URL using VLM"""
    # Fetch image from Cloudinary
    image_bytes = await fetch_image_bytes(image_url)
    image_base64 = encode_image_bytes_to_base64(image_bytes)
    
    # Build the message with image
    messages = [
        {
            "role": "system",
            "content": """You are an expert data analyst skilled at interpreting data visualizations. 
Analyze the provided plot image and extract meaningful insights.

Your response should only include the following, and nothing else:
A title for the analysis of this plot
The following 4 points as a numbered list:
1. **Plot Type**: Identify the type of visualization
2. **Key Observations**: What patterns, trends, or anomalies are visible?
3. **Statistical Insights**: Any notable statistical properties
4. **Actionable Insights**: What decisions or further analyses does this suggest?

Be concise but thorough."""
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"Analyze this data visualization from an EDA of the '{csv_name}' dataset. Plot filename: {plot_filename}"
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{image_base64}"
                    }
                }
            ]
        }
    ]
    
    response = vlm.invoke(messages)
    return response.content


def generate_summary(vlm: ChatGroq, csv_name: str, plot_analyses: List[PlotAnalysis]) -> str:
    """Generate a comprehensive summary from all plot analyses"""
    analyses_text = "\n\n".join([
        f"### {pa.plot_filename}\n{pa.analysis}"
        for pa in plot_analyses
        if pa.status == "success"
    ])
    
    chain = SUMMARY_TEMPLATE | vlm
    response = chain.invoke({
        "dataset_name": csv_name,
        "plot_analyses": analyses_text
    })
    
    return response.content


async def analyze_plots_stream(
    uid: str,
    csv_id: str,
    comment_id: str
) -> Generator[StreamPlotAnalysisResponse, None, None]:
    """
    Analyze all plots for a CSV file using Vision Language Model.
    Fetches plots from MongoDB/Cloudinary and yields analysis for each plot.
    Persists results to MongoDB.
    
    Args:
        uid: User ID for MongoDB persistence
        csv_id: CSV file ID (MongoDB ObjectId string)
        comment_id: Comment ID (MongoDB ObjectId string) - VLM analysis is per-comment
    """
    # Get csv_name for display
    csv_name = get_csv_name_by_id(csv_id)
    
    # Get plots from MongoDB
    plots = get_plots_from_mongodb(csv_id, uid, comment_id)
    
    if not plots:
        yield StreamPlotAnalysisResponse(
            plot_index=0,
            total_plots=0,
            plot_filename="",
            plot_url="",
            analysis="No plots found for this CSV. Run EDA generation first.",
            status="error",
            error="No plots found"
        )
        return
    
    vlm = get_vlm()
    successful_analyses: List[PlotAnalysis] = []
    plot_urls = [p["cloudinary_url"] for p in plots]
    
    for idx, plot in enumerate(plots):
        plot_filename = plot["filename"]
        plot_url = plot["cloudinary_url"]
        
        try:
            analysis = await analyze_single_plot_from_url(vlm, plot_url, plot_filename, csv_name)
            
            plot_analysis = PlotAnalysis(
                plot_filename=plot_filename,
                plot_url=plot_url,
                analysis=analysis,
                status="success"
            )
            successful_analyses.append(plot_analysis)
            
            yield StreamPlotAnalysisResponse(
                plot_index=idx + 1,
                total_plots=len(plots),
                plot_filename=plot_filename,
                plot_url=plot_url,
                analysis=analysis,
                status="success"
            )
            
        except Exception as e:
            yield StreamPlotAnalysisResponse(
                plot_index=idx + 1,
                total_plots=len(plots),
                plot_filename=plot_filename,
                plot_url=plot_url,
                analysis="",
                status="error",
                error=str(e)
            )
    
    # Generate and yield summary
    summary = None
    if successful_analyses:
        try:
            summary = generate_summary(vlm, csv_name, successful_analyses)
            yield StreamPlotAnalysisResponse(
                plot_index=len(plots) + 1,
                total_plots=len(plots),
                plot_filename="summary",
                plot_url="",
                analysis=summary,
                status="success",
                is_summary=True
            )
        except Exception as e:
            yield StreamPlotAnalysisResponse(
                plot_index=len(plots) + 1,
                total_plots=len(plots),
                plot_filename="summary",
                plot_url="",
                analysis="",
                status="error",
                error=f"Failed to generate summary: {str(e)}",
                is_summary=True
            )
    
    # Persist to MongoDB
    if successful_analyses:
        try:
            await save_vlm_analysis_to_db(
                uid=uid,
                csv_id=csv_id,
                comment_id=comment_id,
                plot_urls=plot_urls,
                plot_analyses=[pa.model_dump() for pa in successful_analyses],
                summary=summary,
                overall_status="completed" if successful_analyses else "failed"
            )
        except Exception as e:
            print(f"Failed to save VLM analysis to MongoDB: {e}")


async def analyze_plots_sync(
    uid: str,
    csv_id: str,
    comment_id: str,
    use_cache: bool = True
) -> AnalyzePlotsResponse:
    """
    Analyze all plots for a CSV file synchronously.
    Fetches plots from MongoDB/Cloudinary.
    Supports caching via MongoDB to avoid redundant VLM API calls.
    
    Args:
        uid: User ID for MongoDB persistence/cache
        csv_id: CSV file ID (MongoDB ObjectId string)
        comment_id: Comment ID (MongoDB ObjectId string) - VLM analysis is per-comment
        use_cache: Whether to use cached analysis if available
    """
    # Get csv_name for display
    csv_name = get_csv_name_by_id(csv_id)
    
    # Get plots from MongoDB
    plots = get_plots_from_mongodb(csv_id, uid, comment_id)
    plot_urls = [p["cloudinary_url"] for p in plots] if plots else []
    
    # Check for cached analysis if caching enabled
    if use_cache and uid and csv_id and comment_id:
        cached = get_vlm_analysis_from_db(uid, csv_id, comment_id, plot_urls)
        if cached:
            # Return cached response
            plot_analyses = [
                PlotAnalysis(**pa) for pa in cached.get("plot_analyses", [])
            ]
            return AnalyzePlotsResponse(
                csv_id=csv_id,
                csv_name=csv_name,
                comment_id=comment_id,
                total_plots=cached.get("total_plots", len(plot_analyses)),
                plot_analyses=plot_analyses,
                summary=cached.get("summary"),
                overall_status=cached.get("overall_status", "completed"),
                cached=True
            )
    
    if not plots:
        return AnalyzePlotsResponse(
            csv_id=csv_id,
            csv_name=csv_name,
            comment_id=comment_id,
            total_plots=0,
            plot_analyses=[],
            summary="No plots found for this CSV. Run EDA generation first.",
            overall_status="failed"
        )
    
    vlm = get_vlm()
    plot_analyses: List[PlotAnalysis] = []
    
    for plot in plots:
        plot_filename = plot["filename"]
        plot_url = plot["cloudinary_url"]
        
        try:
            analysis = await analyze_single_plot_from_url(vlm, plot_url, plot_filename, csv_name)
            plot_analyses.append(PlotAnalysis(
                plot_filename=plot_filename,
                plot_url=plot_url,
                analysis=analysis,
                status="success"
            ))
        except Exception as e:
            plot_analyses.append(PlotAnalysis(
                plot_filename=plot_filename,
                plot_url=plot_url,
                analysis="",
                status="error",
                error=str(e)
            ))
    
    # Generate summary
    successful_analyses = [pa for pa in plot_analyses if pa.status == "success"]
    summary = None
    
    if successful_analyses:
        try:
            summary = generate_summary(vlm, csv_name, successful_analyses)
        except Exception as e:
            summary = f"Failed to generate summary: {str(e)}"
    
    overall_status = "completed" if any(pa.status == "success" for pa in plot_analyses) else "failed"
    
    # Persist to MongoDB
    try:
        await save_vlm_analysis_to_db(
            uid=uid,
            csv_id=csv_id,
            comment_id=comment_id,
            plot_urls=plot_urls,
            plot_analyses=[pa.model_dump() for pa in plot_analyses],
            summary=summary,
            overall_status=overall_status
        )
    except Exception as e:
        print(f"Failed to save VLM analysis to MongoDB: {e}")
    
    return AnalyzePlotsResponse(
        csv_id=csv_id,
        csv_name=csv_name,
        comment_id=comment_id,
        total_plots=len(plots),
        plot_analyses=plot_analyses,
        summary=summary,
        overall_status=overall_status,
        cached=False
    )
