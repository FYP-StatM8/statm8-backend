import os
import base64
from typing import List, Generator, Optional
from langchain_groq import ChatGroq
from statm8.constants.stat import GROQ_API_KEY
from statm8.constants.vlm import VLM_MODEL, PLOT_ANALYSIS_TEMPLATE, SUMMARY_TEMPLATE
from statm8.models.vlm import PlotAnalysis, AnalyzePlotsResponse, StreamPlotAnalysisResponse
from statm8.services.export import save_vlm_analysis


def get_vlm():
    """Get VLM instance for vision analysis"""
    return ChatGroq(
        model=VLM_MODEL,
        temperature=0.3,
        max_retries=2,
        api_key=GROQ_API_KEY
    )


def get_plot_dir_from_dataset(dataset_name: str) -> str:
    """
    Generate plot directory path from dataset name.
    Example: iris -> outputs/plots/iris
    """
    return os.path.join("outputs", "plots", dataset_name)


def get_plots_in_directory(plot_dir: str) -> List[str]:
    """Get list of plot files in a directory"""
    if not os.path.exists(plot_dir):
        return []
    
    plot_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
    plots = []
    
    for filename in sorted(os.listdir(plot_dir)):
        ext = os.path.splitext(filename)[1].lower()
        if ext in plot_extensions:
            plots.append(filename)
    
    return plots


def encode_image_to_base64(image_path: str) -> str:
    """Encode an image file to base64 string"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def analyze_single_plot(
    vlm: ChatGroq,
    image_path: str,
    plot_filename: str,
    dataset_name: str
) -> str:
    """Analyze a single plot image using VLM"""
    image_base64 = encode_image_to_base64(image_path)
    
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
                    "text": f"Analyze this data visualization from an EDA of the '{dataset_name}' dataset. Plot filename: {plot_filename}"
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


def generate_summary(vlm: ChatGroq, dataset_name: str, plot_analyses: List[PlotAnalysis]) -> str:
    """Generate a comprehensive summary from all plot analyses"""
    analyses_text = "\n\n".join([
        f"### {pa.plot_filename}\n{pa.analysis}"
        for pa in plot_analyses
        if pa.status == "success"
    ])
    
    chain = SUMMARY_TEMPLATE | vlm
    response = chain.invoke({
        "dataset_name": dataset_name,
        "plot_analyses": analyses_text
    })
    
    return response.content


def analyze_plots_stream(
    dataset_name: str,
    plot_dir: Optional[str] = None
) -> Generator[StreamPlotAnalysisResponse, None, None]:
    """
    Analyze all plots in a directory with streaming response.
    Yields analysis for each plot as it's processed.
    """
    if plot_dir is None:
        plot_dir = get_plot_dir_from_dataset(dataset_name)
    
    plots = get_plots_in_directory(plot_dir)
    
    if not plots:
        yield StreamPlotAnalysisResponse(
            plot_index=0,
            total_plots=0,
            plot_filename="",
            plot_path=plot_dir,
            analysis="No plots found in the specified directory.",
            status="error",
            error="No plots found"
        )
        return
    
    vlm = get_vlm()
    successful_analyses: List[PlotAnalysis] = []
    
    for idx, plot_filename in enumerate(plots):
        plot_path = os.path.join(plot_dir, plot_filename)
        
        try:
            analysis = analyze_single_plot(vlm, plot_path, plot_filename, dataset_name)
            
            plot_analysis = PlotAnalysis(
                plot_filename=plot_filename,
                plot_path=plot_path,
                analysis=analysis,
                status="success"
            )
            successful_analyses.append(plot_analysis)
            
            yield StreamPlotAnalysisResponse(
                plot_index=idx + 1,
                total_plots=len(plots),
                plot_filename=plot_filename,
                plot_path=plot_path,
                analysis=analysis,
                status="success"
            )
            
        except Exception as e:
            yield StreamPlotAnalysisResponse(
                plot_index=idx + 1,
                total_plots=len(plots),
                plot_filename=plot_filename,
                plot_path=plot_path,
                analysis="",
                status="error",
                error=str(e)
            )
    
    # Generate and yield summary
    summary = None
    if successful_analyses:
        try:
            summary = generate_summary(vlm, dataset_name, successful_analyses)
            yield StreamPlotAnalysisResponse(
                plot_index=len(plots) + 1,
                total_plots=len(plots),
                plot_filename="summary",
                plot_path=plot_dir,
                analysis=summary,
                status="success",
                is_summary=True
            )
        except Exception as e:
            yield StreamPlotAnalysisResponse(
                plot_index=len(plots) + 1,
                total_plots=len(plots),
                plot_filename="summary",
                plot_path=plot_dir,
                analysis="",
                status="error",
                error=f"Failed to generate summary: {str(e)}",
                is_summary=True
            )
    
    # Save VLM analysis to disk for export
    if successful_analyses:
        analysis_data = {
            "dataset_name": dataset_name,
            "plot_dir": plot_dir,
            "total_plots": len(plots),
            "plot_analyses": [pa.model_dump() for pa in successful_analyses],
            "summary": summary,
            "overall_status": "completed" if successful_analyses else "failed"
        }
        save_vlm_analysis(dataset_name, analysis_data)


def analyze_plots_sync(
    dataset_name: str,
    plot_dir: Optional[str] = None
) -> AnalyzePlotsResponse:
    """
    Analyze all plots in a directory synchronously.
    Returns complete analysis in a single response.
    """
    if plot_dir is None:
        plot_dir = get_plot_dir_from_dataset(dataset_name)
    
    plots = get_plots_in_directory(plot_dir)
    
    if not plots:
        return AnalyzePlotsResponse(
            dataset_name=dataset_name,
            plot_dir=plot_dir,
            total_plots=0,
            plot_analyses=[],
            summary="No plots found in the specified directory.",
            overall_status="failed"
        )
    
    vlm = get_vlm()
    plot_analyses: List[PlotAnalysis] = []
    
    for plot_filename in plots:
        plot_path = os.path.join(plot_dir, plot_filename)
        
        try:
            analysis = analyze_single_plot(vlm, plot_path, plot_filename, dataset_name)
            plot_analyses.append(PlotAnalysis(
                plot_filename=plot_filename,
                plot_path=plot_path,
                analysis=analysis,
                status="success"
            ))
        except Exception as e:
            plot_analyses.append(PlotAnalysis(
                plot_filename=plot_filename,
                plot_path=plot_path,
                analysis="",
                status="error",
                error=str(e)
            ))
    
    # Generate summary
    successful_analyses = [pa for pa in plot_analyses if pa.status == "success"]
    summary = None
    
    if successful_analyses:
        try:
            summary = generate_summary(vlm, dataset_name, successful_analyses)
        except Exception as e:
            summary = f"Failed to generate summary: {str(e)}"
    
    overall_status = "completed" if any(pa.status == "success" for pa in plot_analyses) else "failed"
    
    # Save VLM analysis to disk for export
    analysis_data = {
        "dataset_name": dataset_name,
        "plot_dir": plot_dir,
        "total_plots": len(plots),
        "plot_analyses": [pa.model_dump() for pa in plot_analyses],
        "summary": summary,
        "overall_status": overall_status
    }
    save_vlm_analysis(dataset_name, analysis_data)
    
    return AnalyzePlotsResponse(
        dataset_name=dataset_name,
        plot_dir=plot_dir,
        total_plots=len(plots),
        plot_analyses=plot_analyses,
        summary=summary,
        overall_status=overall_status
    )
