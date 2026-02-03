import os
import re
import json
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple, Literal
from fpdf import FPDF
from PIL import Image
import markdown as md

from statm8.models.export import ExportResponse, ExportStatusResponse, PlotInfo


def convert_markdown_to_html(text: str) -> str:
    """
    Convert markdown text to HTML for PDF rendering.
    Uses the markdown library with extensions for tables, fenced code, and newlines.
    """
    if not text:
        return text
    
    # Convert markdown to HTML with useful extensions
    html = md.markdown(
        text,
        extensions=['tables', 'fenced_code', 'nl2br', 'sane_lists']
    )
    
    # fpdf2's write_html has limited <pre>/<code> support
    # Replace <code> with monospace font tags for better rendering
    html = html.replace('<code>', '<font face="Courier" size="9">')
    html = html.replace('</code>', '</font>')
    
    # Handle <pre> blocks (from fenced code blocks)
    html = html.replace('<pre>', '<font face="Courier" size="9">')
    html = html.replace('</pre>', '</font><br>')
    
    return html


class EDAReportPDF(FPDF):
    """Custom PDF class for EDA reports"""
    
    def __init__(self, title: str = "EDA Report"):
        super().__init__()
        self.report_title = title
        self.set_auto_page_break(auto=True, margin=15)
        
    def header(self):
        self.set_font('Helvetica', 'B', 12)
        self.cell(0, 10, self.report_title, 0, 1, 'C')
        self.ln(5)
        
    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', 0, 0, 'C')
        
    def chapter_title(self, title: str):
        self.set_font('Helvetica', 'B', 14)
        self.set_fill_color(240, 240, 240)
        self.cell(0, 10, title, 0, 1, 'L', fill=True)
        self.ln(4)
        
    def chapter_body(self, text: str, render_markdown: bool = True):
        self.set_font('Helvetica', '', 10)
        
        if render_markdown and text:
            # Convert markdown to HTML and render with write_html
            html = convert_markdown_to_html(text)
            self.write_html(html)
        else:
            # Fallback to plain text rendering
            text = text.encode('latin-1', 'replace').decode('latin-1')
            self.multi_cell(0, 5, text)
        
        self.ln()
        
    def add_plot(self, image_path: str, caption: str = ""):
        """Add a plot image to the PDF"""
        if not os.path.exists(image_path):
            return
            
        try:
            # Get image dimensions to scale properly
            with Image.open(image_path) as img:
                img_width, img_height = img.size
            
            # Calculate scaling to fit page width (max 180mm)
            max_width = 180
            max_height = 120
            
            aspect_ratio = img_width / img_height
            
            if aspect_ratio > max_width / max_height:
                # Width limited
                pdf_width = max_width
                pdf_height = max_width / aspect_ratio
            else:
                # Height limited
                pdf_height = max_height
                pdf_width = max_height * aspect_ratio
            
            # Check if we need a new page
            if self.get_y() + pdf_height + 20 > self.h - 20:
                self.add_page()
            
            # Center the image
            x_pos = (self.w - pdf_width) / 2
            self.image(image_path, x=x_pos, w=pdf_width)
            
            if caption:
                self.set_font('Helvetica', 'I', 9)
                caption = caption.encode('latin-1', 'replace').decode('latin-1')
                self.cell(0, 10, caption, 0, 1, 'C')
            
            self.ln(5)
            
        except Exception as e:
            self.chapter_body(f"[Error loading image: {str(e)}]")


def get_dataset_paths(dataset_name: str) -> Dict[str, str]:
    """Get all relevant paths for a dataset"""
    return {
        "summary_json": os.path.join("uploads", f"{dataset_name}.json"),
        "data_csv": os.path.join("uploads", f"{dataset_name}.csv"),
        "plot_dir": os.path.join("outputs", "plots", dataset_name),
        "vlm_analysis": os.path.join("outputs", "vlm", f"{dataset_name}_analysis.json"),
        "export_dir": os.path.join("outputs", "exports")
    }


def check_export_status(dataset_name: str) -> ExportStatusResponse:
    """Check what data is available for export"""
    paths = get_dataset_paths(dataset_name)
    
    has_summary = os.path.exists(paths["summary_json"])
    has_plots = os.path.exists(paths["plot_dir"])
    plot_count = 0
    
    if has_plots:
        plot_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
        for f in os.listdir(paths["plot_dir"]):
            if os.path.splitext(f)[1].lower() in plot_extensions:
                plot_count += 1
    
    has_vlm = os.path.exists(paths["vlm_analysis"])
    
    return ExportStatusResponse(
        dataset_name=dataset_name,
        has_summary=has_summary,
        summary_path=paths["summary_json"] if has_summary else None,
        has_plots=has_plots and plot_count > 0,
        plot_count=plot_count,
        plot_dir=paths["plot_dir"] if has_plots else None,
        has_vlm_analysis=has_vlm,
        vlm_analysis_path=paths["vlm_analysis"] if has_vlm else None,
        can_export=has_summary or (has_plots and plot_count > 0)
    )


def load_dataset_summary(summary_path: str) -> Optional[Dict[str, Any]]:
    """Load dataset summary from JSON file"""
    if not os.path.exists(summary_path):
        return None
    
    with open(summary_path, 'r') as f:
        return json.load(f)


def load_vlm_analysis(vlm_path: str) -> Optional[Dict[str, Any]]:
    """Load VLM analysis from JSON file"""
    if not os.path.exists(vlm_path):
        return None
    
    with open(vlm_path, 'r') as f:
        return json.load(f)


def get_plots_in_directory(plot_dir: str) -> List[PlotInfo]:
    """Get list of plots in directory"""
    if not os.path.exists(plot_dir):
        return []
    
    plot_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
    plots = []
    
    for filename in sorted(os.listdir(plot_dir)):
        ext = os.path.splitext(filename)[1].lower()
        if ext in plot_extensions:
            plots.append(PlotInfo(
                filename=filename,
                path=os.path.join(plot_dir, filename)
            ))
    
    return plots


def save_vlm_analysis(dataset_name: str, analysis_data: Dict[str, Any]):
    """Save VLM analysis to JSON for later export use"""
    paths = get_dataset_paths(dataset_name)
    vlm_dir = os.path.dirname(paths["vlm_analysis"])
    
    os.makedirs(vlm_dir, exist_ok=True)
    
    with open(paths["vlm_analysis"], 'w') as f:
        json.dump(analysis_data, f, indent=2)


def generate_pdf_report(
    dataset_name: str,
    include_summary: bool = True,
    include_plots: bool = True,
    include_vlm_analysis: bool = False,
    include_code: bool = False,
    custom_title: Optional[str] = None
) -> ExportResponse:
    """
    Generate a PDF report for the EDA results.
    
    Args:
        dataset_name: Name of the dataset
        include_summary: Include dataset summary section
        include_plots: Include generated plots
        include_vlm_analysis: Include VLM plot analyses
        include_code: Include generated code blocks
        custom_title: Custom title for the report
    
    Returns:
        ExportResponse with path to generated PDF
    """
    paths = get_dataset_paths(dataset_name)
    
    # Ensure export directory exists
    os.makedirs(paths["export_dir"], exist_ok=True)
    
    # Generate PDF filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_filename = f"{dataset_name}_eda_report_{timestamp}.pdf"
    pdf_path = os.path.join(paths["export_dir"], pdf_filename)
    
    # Create PDF
    title = custom_title or f"EDA Report: {dataset_name}"
    pdf = EDAReportPDF(title=title)
    pdf.alias_nb_pages()
    pdf.add_page()
    
    sections_included = []
    total_plots = 0
    
    # Title page info
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(0, 10, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 0, 1, 'C')
    pdf.cell(0, 10, f"Dataset: {dataset_name}", 0, 1, 'C')
    pdf.ln(10)
    
    # Dataset Summary Section
    if include_summary:
        summary_data = load_dataset_summary(paths["summary_json"])
        if summary_data:
            sections_included.append("summary")
            
            pdf.chapter_title("Dataset Overview")
            
            # Basic info
            overview_text = f"""
File Type: {summary_data.get('file_type', 'N/A')}
Total Rows: {summary_data.get('total_rows', 'N/A')}
Total Columns: {summary_data.get('total_columns', 'N/A')}
            """.strip()
            pdf.chapter_body(overview_text, False)
            
            # Column information
            if 'columns_info' in summary_data:
                pdf.chapter_title("Column Information")
                for col in summary_data['columns_info']:
                    col_text = f"- {col.get('name', 'N/A')}: {col.get('dtype', 'N/A')} ({col.get('non_null_count', 'N/A')} non-null)"
                    pdf.chapter_body(col_text)
            
            # AI Summary
            if 'ai_summary' in summary_data and summary_data['ai_summary']:
                pdf.chapter_title("AI-Generated Summary")
                pdf.chapter_body(summary_data['ai_summary'])
    
    # Plots Section
    if include_plots:
        plots = get_plots_in_directory(paths["plot_dir"])
        if plots:
            sections_included.append("plots")
            total_plots = len(plots)
            
            pdf.add_page()
            pdf.chapter_title("Generated Visualizations")
            
            # Load VLM analysis if available and requested
            vlm_data = None
            if include_vlm_analysis:
                vlm_data = load_vlm_analysis(paths["vlm_analysis"])
                if vlm_data:
                    sections_included.append("vlm_analysis")
            
            for idx , plot in enumerate(plots):
                # Add a new page if not the first plot
                if idx > 0:
                    pdf.add_page()
                # Add VLM analysis if available
                if vlm_data and 'plot_analyses' in vlm_data:
                    for analysis in vlm_data['plot_analyses']:
                        if analysis.get('plot_filename') == plot.filename:
                            if analysis.get('analysis'):
                                pdf.set_font('Helvetica', 'I', 9)
                                pdf.chapter_body(analysis['analysis'])
                            break
                # Add plot image
                pdf.add_plot(plot.path, caption=plot.filename)
            
            # Add VLM summary if available
            if vlm_data and 'summary' in vlm_data and vlm_data['summary']:
                pdf.add_page()
                pdf.chapter_title("VLM Analysis Summary")
                pdf.chapter_body(vlm_data['summary'])
    
    # Save PDF
    pdf.output(pdf_path)
    
    # Get file size
    file_size = os.path.getsize(pdf_path)
    
    return ExportResponse(
        dataset_name=dataset_name,
        export_path=pdf_path,
        file_size_bytes=file_size,
        sections_included=sections_included,
        total_plots=total_plots,
        generated_at=datetime.now().isoformat(),
        status="success"
    )


def generate_markdown_report(
    dataset_name: str,
    include_summary: bool = True,
    include_plots: bool = True,
    include_vlm_analysis: bool = False,
    include_code: bool = False,
    custom_title: Optional[str] = None
) -> ExportResponse:
    """
    Generate a Markdown report for the EDA results.
    Preserves original AI-generated markdown formatting.
    
    Args:
        dataset_name: Name of the dataset
        include_summary: Include dataset summary section
        include_plots: Include generated plots
        include_vlm_analysis: Include VLM plot analyses
        include_code: Include generated code blocks
        custom_title: Custom title for the report
    
    Returns:
        ExportResponse with path to generated Markdown file
    """
    paths = get_dataset_paths(dataset_name)
    
    # Ensure export directory exists
    os.makedirs(paths["export_dir"], exist_ok=True)
    
    # Generate Markdown filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_filename = f"{dataset_name}_eda_report_{timestamp}.md"
    md_path = os.path.join(paths["export_dir"], md_filename)
    
    sections_included = []
    total_plots = 0
    
    # Build markdown content
    lines = []
    
    # Title
    title = custom_title or f"EDA Report: {dataset_name}"
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Dataset:** {dataset_name}")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Dataset Summary Section
    if include_summary:
        summary_data = load_dataset_summary(paths["summary_json"])
        if summary_data:
            sections_included.append("summary")
            
            lines.append("## Dataset Overview")
            lines.append("")
            lines.append(f"- **File Type:** {summary_data.get('file_type', 'N/A')}")
            lines.append(f"- **Total Rows:** {summary_data.get('total_rows', 'N/A')}")
            lines.append(f"- **Total Columns:** {summary_data.get('total_columns', 'N/A')}")
            lines.append("")
            
            # Column information as a table
            if 'columns_info' in summary_data and summary_data['columns_info']:
                lines.append("## Column Information")
                lines.append("")
                lines.append("| Column Name | Data Type | Non-Null Count | Unique Count |")
                lines.append("|-------------|-----------|----------------|--------------|")
                
                for col in summary_data['columns_info']:
                    name = col.get('name', 'N/A')
                    dtype = col.get('dtype', 'N/A')
                    non_null = col.get('non_null_count', 'N/A')
                    unique = col.get('unique_count', 'N/A')
                    lines.append(f"| {name} | {dtype} | {non_null} | {unique} |")
                
                lines.append("")
            
            # AI Summary - preserve original markdown formatting
            if 'ai_summary' in summary_data and summary_data['ai_summary']:
                lines.append("## AI-Generated Summary")
                lines.append("")
                lines.append(summary_data['ai_summary'])
                lines.append("")
    
    # Plots Section
    if include_plots:
        plots = get_plots_in_directory(paths["plot_dir"])
        if plots:
            sections_included.append("plots")
            total_plots = len(plots)
            
            lines.append("---")
            lines.append("")
            lines.append("## Generated Visualizations")
            lines.append("")
            
            # Load VLM analysis if available and requested
            vlm_data = None
            if include_vlm_analysis:
                vlm_data = load_vlm_analysis(paths["vlm_analysis"])
                if vlm_data:
                    sections_included.append("vlm_analysis")
            
            for plot in plots:
                # Add VLM analysis if available - preserve original markdown
                if vlm_data and 'plot_analyses' in vlm_data:
                    for analysis in vlm_data['plot_analyses']:
                        if analysis.get('plot_filename') == plot.filename:
                            if analysis.get('analysis'):
                                # lines.append("#### Analysis")
                                # lines.append("")
                                lines.append(analysis['analysis'])
                                # lines.append("")
                            break
                # Add plot image with relative path
                plot_relative_path = os.path.relpath(plot.path, paths["export_dir"])
                lines.append(f"### {plot.filename}")
                lines.append("")
                lines.append(f"![{plot.filename}]({plot_relative_path})")
                lines.append("")
                
            
            # Add VLM summary if available - preserve original markdown
            if vlm_data and 'summary' in vlm_data and vlm_data['summary']:
                lines.append("---")
                lines.append("")
                lines.append("## VLM Analysis Summary")
                lines.append("")
                lines.append(vlm_data['summary'])
                lines.append("")
    
    # Write markdown file
    md_content = '\n'.join(lines)
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
    
    # Get file size
    file_size = os.path.getsize(md_path)
    
    return ExportResponse(
        dataset_name=dataset_name,
        export_path=md_path,
        file_size_bytes=file_size,
        sections_included=sections_included,
        total_plots=total_plots,
        generated_at=datetime.now().isoformat(),
        status="success"
    )
