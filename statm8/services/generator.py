import pandas as pd
import os
import io
import sys
import time
import json
import tempfile
import traceback
import re
import subprocess
from contextlib import redirect_stdout, redirect_stderr
from typing import List, Dict, Any, Generator, Optional, Tuple
from statm8.models.generator import CodeBlock, GenerateEDAResponse, StreamCodeBlockResponse
from statm8.constants.stat import llm
from statm8.constants.generator import EDA_CODE_GENERATION_TEMPLATE
from statm8.services.storage import (
    upload_plot_to_cloudinary,
    save_plot_to_db,
    get_csv_name_by_id
)

# Execution timeout in seconds
EXECUTION_TIMEOUT = 60
# Maximum failures before skipping a block
MAX_FAILURES_BEFORE_SKIP = 3


def get_dataset_name_from_filepath(file_path: str) -> str:
    """Extract dataset name from file path."""
    return os.path.splitext(os.path.basename(file_path))[0]


def get_output_dir_from_filepath(file_path: str) -> str:
    """
    Generate a temporary output directory path from input file path.
    This is used for temporary plot storage before Cloudinary upload.
    """
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    # Use system temp directory
    output_dir = os.path.join(tempfile.gettempdir(), "statm8_plots", base_name)
    return output_dir


def clean_code(code: str) -> str:
    """Remove markdown code fences and clean up code"""
    # Remove markdown code fences
    code = re.sub(r'^```python\s*\n', '', code, flags=re.MULTILINE)
    code = re.sub(r'^```\s*\n', '', code, flags=re.MULTILINE)
    code = re.sub(r'\n```\s*$', '', code, flags=re.MULTILINE)
    code = code.strip()
    return code


def get_dataset_info(file_path: str) -> Dict[str, Any]:
    """Extract dataset information for code generation"""
    df = pd.read_csv(file_path)
    
    columns_info = []
    for col in df.columns:
        col_info = {
            "name": col,
            "dtype": str(df[col].dtype),
            "non_null": int(df[col].notna().sum()),
            "null": int(df[col].isna().sum()),
            "unique": int(df[col].nunique())
        }
        if pd.api.types.is_numeric_dtype(df[col]):
            col_info["min"] = float(df[col].min())
            col_info["max"] = float(df[col].max())
            col_info["mean"] = float(df[col].mean())
        columns_info.append(col_info)
    
    sample_rows = df.head(3).to_dict('records')
    
    return {
        "total_rows": len(df),
        "total_columns": len(df.columns),
        "columns_info": json.dumps(columns_info, indent=2),
        "sample_rows": json.dumps(sample_rows, indent=2)
    }


def regenerate_single_code_block(file_path: str, output_dir: str, error_msg: str, previous_code: str, description: str) -> str:
    """Regenerate a single code block that failed"""
    from langchain_core.prompts import ChatPromptTemplate
    
    regeneration_prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an expert data scientist. A previous code block failed to execute.
Generate a CORRECTED version that fixes the error.

CRITICAL RULES:
1. Return ONLY pure Python code - NO markdown code fences (no ```python or ```)
2. Use 'df' as the DataFrame variable name
3. Use pandas, matplotlib, seaborn, numpy
4. Save plots using: plt.savefig(os.path.join(output_dir, 'plot_name.png'), bbox_inches='tight', dpi=300)
5. Always close plots: plt.close()
6. Include proper error handling"""),
        
        ("user", """File Path: {file_path}
Output Directory: {output_dir}
Task Description: {description}

Previous Code (FAILED):
{previous_code}

Error Message:
{error_msg}

Generate CORRECTED Python code. Return ONLY the code, NO markdown formatting, NO explanations.""")
    ])
    
    chain = regeneration_prompt | llm
    response = chain.invoke({
        "file_path": file_path,
        "output_dir": output_dir,
        "description": description,
        "previous_code": previous_code,
        "error_msg": error_msg
    })
    
    regenerated_code = clean_code(response.content)
    return regenerated_code


def generate_eda_code_blocks(file_path: str, output_dir: str, comments: Optional[str] = None) -> List[CodeBlock]:
    """Generate EDA code blocks using LLM"""
    dataset_info = get_dataset_info(file_path)
    
    # Prepare comments section
    comments_section = ""
    if comments:
        comments_section = f"User Comments/Instructions:\n{comments}\n\nPlease take these comments into consideration when generating the EDA code."
    
    chain = EDA_CODE_GENERATION_TEMPLATE | llm
    response = chain.invoke({
        "file_path": file_path,
        "output_dir": output_dir,
        "comments_section": comments_section,
        **dataset_info
    })
    
    # Parse the response into code blocks
    raw_blocks = response.content.split("### BLOCK_SEPARATOR ###")
    
    code_blocks = []
    for idx, block_content in enumerate(raw_blocks):
        block_content = block_content.strip()
        if not block_content:
            continue
            
        # Extract description from first comment line
        lines = block_content.split('\n')
        description = "EDA Analysis Block"
        code_lines = []
        
        for line in lines:
            if line.strip().startswith('#') and not code_lines:
                description = line.strip('# ').strip()
            else:
                code_lines.append(line)
        
        code = '\n'.join(code_lines).strip()
        
        # Clean code (remove markdown fences)
        code = clean_code(code)
        
        # Ensure proper imports and setup
        if 'import' not in code:
            code = f"""import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import os

df = pd.read_csv('{file_path}')
output_dir = '{output_dir}'

{code}"""
        
        code_blocks.append(CodeBlock(
            id=idx + 1,
            description=description,
            code=code,
            status="pending"
        ))
    
    return code_blocks


def _build_executable_code(code: str, file_path: str, output_dir: str) -> str:
    """
    Build a complete executable Python script with proper imports and matplotlib backend.
    Forces non-interactive Agg backend to prevent GUI-related hangs.
    """
    # Check if code already has imports
    has_imports = 'import pandas' in code or 'import matplotlib' in code
    
    if has_imports:
        # Inject matplotlib backend at the very beginning
        return f"""import matplotlib
matplotlib.use('Agg')  # Force non-interactive backend
{code}"""
    else:
        # Full setup with imports
        return f"""import matplotlib
matplotlib.use('Agg')  # Force non-interactive backend
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import os

df = pd.read_csv('{file_path}')
output_dir = '{output_dir}'

{code}"""


def _execute_code_in_subprocess(code: str, timeout: int = EXECUTION_TIMEOUT) -> Tuple[str, str, int, bool]:
    """
    Execute Python code in a subprocess with timeout.
    
    Returns:
        Tuple of (stdout, stderr, return_code, timed_out)
    """
    # Create a temporary file to hold the code
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        temp_script_path = f.name
    
    try:
        result = subprocess.run(
            [sys.executable, temp_script_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.path.dirname(temp_script_path)
        )
        return result.stdout, result.stderr, result.returncode, False
    except subprocess.TimeoutExpired:
        return "", f"Execution timed out after {timeout} seconds", -1, True
    except Exception as e:
        return "", f"Subprocess execution failed: {str(e)}", -1, False
    finally:
        # Cleanup temporary script file
        try:
            os.unlink(temp_script_path)
        except:
            pass


def execute_code_block(code_block: CodeBlock, file_path: str, output_dir: str, max_retries: int = MAX_FAILURES_BEFORE_SKIP - 1) -> CodeBlock:
    """
    Execute a single code block with retry logic using subprocess for isolation and timeout.
    Plots are saved temporarily then uploaded to Cloudinary.
    Skips block after MAX_FAILURES_BEFORE_SKIP (3) consecutive failures.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    current_code = code_block.code
    attempt = 0
    total_failures = 0
    
    while attempt <= max_retries and total_failures < MAX_FAILURES_BEFORE_SKIP:
        # Track plots before execution
        plots_before = set(os.listdir(output_dir)) if os.path.exists(output_dir) else set()
        
        # Build executable code with proper matplotlib backend
        executable_code = _build_executable_code(current_code, file_path, output_dir)
        
        start_time = time.time()
        code_block.status = "executing"
        
        # Execute in subprocess with timeout
        stdout, stderr, return_code, timed_out = _execute_code_in_subprocess(
            executable_code, 
            timeout=EXECUTION_TIMEOUT
        )
        
        execution_time = time.time() - start_time
        
        if return_code == 0 and not timed_out:
            # Success
            plots_after = set(os.listdir(output_dir)) if os.path.exists(output_dir) else set()
            new_plots = list(plots_after - plots_before)
            
            code_block.status = "success"
            code_block.code = current_code
            code_block.output = stdout
            code_block.execution_time = round(execution_time, 2)
            code_block.plots_generated = new_plots
            
            if attempt > 0:
                code_block.output = f"[Regenerated after {attempt} attempt(s)]\n" + code_block.output
            
            return code_block
        else:
            # Failure - either error or timeout
            total_failures += 1
            
            if timed_out:
                error_msg = f"Execution timed out after {EXECUTION_TIMEOUT} seconds. The code may contain infinite loops, heavy computations, or blocking calls."
            else:
                error_msg = stderr if stderr else f"Execution failed with return code {return_code}"
            
            print(f"Block {code_block.id} failed (attempt {attempt + 1}/{max_retries + 1}, total failures: {total_failures}/{MAX_FAILURES_BEFORE_SKIP}): {error_msg[:200]}...")
            
            # Check if we should skip this block entirely
            if total_failures >= MAX_FAILURES_BEFORE_SKIP:
                code_block.status = "skipped"
                code_block.error = f"Skipped after {MAX_FAILURES_BEFORE_SKIP} consecutive failures.\n\nLast error:\n{error_msg}"
                code_block.execution_time = round(execution_time, 2)
                code_block.output = stdout
                return code_block
            
            if attempt < max_retries:
                try:
                    current_code = regenerate_single_code_block(
                        file_path=file_path,
                        output_dir=output_dir,
                        error_msg=error_msg,
                        previous_code=current_code,
                        description=code_block.description
                    )
                    attempt += 1
                    continue
                except Exception as regen_error:
                    print(f"Regeneration failed: {regen_error}")
                    total_failures += 1
                    attempt += 1
                    continue
            else:
                code_block.status = "error"
                code_block.error = f"Failed after {max_retries + 1} attempts.\n\nFinal error:\n{error_msg}"
                code_block.execution_time = round(execution_time, 2)
                code_block.output = stdout
                return code_block
    
    # Fallback - should not reach here normally
    code_block.status = "skipped"
    code_block.error = f"Skipped after {total_failures} failures"
    return code_block


async def upload_plots_from_block(
    output_dir: str,
    plot_filenames: List[str],
    uid: str,
    csv_id: str,
    code_block_id: int,
    description: str,
    comment_id: Optional[str] = None
) -> List[Dict[str, str]]:
    """
    Upload plots generated by a code block to Cloudinary and save metadata to MongoDB.
    
    Args:
        output_dir: Temporary directory containing the plots
        plot_filenames: List of plot filenames to upload
        uid: User ID
        csv_id: CSV file ID (MongoDB ObjectId string)
        code_block_id: ID of the code block that generated these plots
        description: Description of the code block
        comment_id: Optional comment ID for associating plot with specific analysis
    
    Returns:
        List of dicts with filename and cloudinary_url
    """
    # Get csv_name for Cloudinary folder naming
    csv_name = get_csv_name_by_id(csv_id)
    uploaded_plots = []
    
    for filename in plot_filenames:
        plot_path = os.path.join(output_dir, filename)
        if not os.path.exists(plot_path):
            continue
        
        try:
            # Read the plot file
            with open(plot_path, 'rb') as f:
                image_bytes = f.read()
            
            # Upload to Cloudinary (use csv_name for folder structure)
            upload_result = await upload_plot_to_cloudinary(
                image_bytes=image_bytes,
                filename=filename,
                dataset_name=csv_name  # Use csv_name for Cloudinary folder
            )
            
            # Save to MongoDB
            await save_plot_to_db(
                uid=uid,
                csv_id=csv_id,
                filename=filename,
                cloudinary_url=upload_result["cloudinary_url"],
                public_id=upload_result["public_id"],
                code_block_id=code_block_id,
                description=description,
                comment_id=comment_id
            )
            
            uploaded_plots.append({
                "filename": filename,
                "cloudinary_url": upload_result["cloudinary_url"]
            })
            
            # Remove the temporary file after upload
            os.remove(plot_path)
            
        except Exception as e:
            print(f"Failed to upload plot {filename}: {e}")
    
    return uploaded_plots


def cleanup_temp_dir(output_dir: str):
    """Clean up temporary plot directory."""
    import shutil
    try:
        if os.path.exists(output_dir) and output_dir.startswith(tempfile.gettempdir()):
            shutil.rmtree(output_dir)
    except Exception as e:
        print(f"Failed to cleanup temp dir {output_dir}: {e}")


async def generate_and_execute_eda_with_upload(
    file_path: str,
    output_dir: str,
    comments: Optional[str],
    max_retries: int,
    uid: str,
    csv_id: str,
    comment_id: Optional[str] = None
):
    """
    Generate and execute EDA code blocks, streaming results.
    Uploads plots to Cloudinary immediately after each block.
    
    Args:
        file_path: Path to local CSV file (temporary)
        output_dir: Output directory for plots
        comments: Optional user comments
        max_retries: Maximum number of regeneration attempts
        uid: User ID
        csv_id: CSV file ID (MongoDB ObjectId string)
        comment_id: Optional comment ID for associating plots with specific analysis
    """
    # Generate code blocks
    yield StreamCodeBlockResponse(
        block_id=0,
        description="Generating EDA code blocks...",
        code="",
        status="generating"
    )
    
    code_blocks = generate_eda_code_blocks(file_path, output_dir, comments)
    
    try:
        # Execute each block and stream results
        for block in code_blocks:
            # Stream block before execution
            yield StreamCodeBlockResponse(
                block_id=block.id,
                description=block.description,
                code=block.code,
                status="executing"
            )
            
            # Execute block with retry logic
            executed_block = execute_code_block(block, file_path, output_dir, max_retries)
            
            # Upload plots to Cloudinary if execution was successful
            plot_urls = []
            if executed_block.status == "success" and executed_block.plots_generated:
                uploaded = await upload_plots_from_block(
                    output_dir=output_dir,
                    plot_filenames=executed_block.plots_generated,
                    uid=uid,
                    csv_id=csv_id,
                    code_block_id=executed_block.id,
                    description=executed_block.description,
                    comment_id=comment_id
                )
                plot_urls = [p["cloudinary_url"] for p in uploaded]
            
            # Stream results after execution
            yield StreamCodeBlockResponse(
                block_id=executed_block.id,
                description=executed_block.description,
                code=executed_block.code,
                status=executed_block.status,
                output=executed_block.output,
                error=executed_block.error,
                plots_generated=executed_block.plots_generated,
                plot_urls=plot_urls
            )
    finally:
        # Cleanup temporary directory
        cleanup_temp_dir(output_dir)


def generate_and_execute_eda(file_path: str, output_dir: str, comments: Optional[str] = None, max_retries: int = 2) -> Generator[StreamCodeBlockResponse, None, None]:
    """
    Generate and execute EDA code blocks, streaming results.
    NOTE: This is the legacy version that doesn't upload to Cloudinary.
    Use generate_and_execute_eda_with_upload for cloud storage.
    """
    dataset_name = get_dataset_name_from_filepath(file_path)
    
    # Generate code blocks
    yield StreamCodeBlockResponse(
        block_id=0,
        description="Generating EDA code blocks...",
        code="",
        status="generating"
    )
    
    code_blocks = generate_eda_code_blocks(file_path, output_dir, comments)
    
    # Execute each block and stream results
    for block in code_blocks:
        # Stream block before execution
        yield StreamCodeBlockResponse(
            block_id=block.id,
            description=block.description,
            code=block.code,
            status="executing"
        )
        
        # Execute block with retry logic
        executed_block = execute_code_block(block, file_path, output_dir, max_retries)
        
        # Stream results after execution
        yield StreamCodeBlockResponse(
            block_id=executed_block.id,
            description=executed_block.description,
            code=executed_block.code,
            status=executed_block.status,
            output=executed_block.output,
            error=executed_block.error,
            plots_generated=executed_block.plots_generated
        )


async def generate_and_execute_eda_sync_with_upload(
    file_path: str,
    output_dir: str,
    comments: Optional[str],
    max_retries: int,
    uid: str,
    csv_id: str,
    comment_id: Optional[str] = None
) -> GenerateEDAResponse:
    """
    Generate and execute EDA code blocks synchronously with Cloudinary upload.
    
    Args:
        file_path: Path to local CSV file (temporary)
        output_dir: Output directory for plots
        comments: Optional user comments
        max_retries: Maximum number of regeneration attempts
        uid: User ID
        csv_id: CSV file ID (MongoDB ObjectId string)
        comment_id: Optional comment ID for associating plots with specific analysis
    """
    # Get csv_name for response
    csv_name = get_csv_name_by_id(csv_id)
    
    code_blocks = generate_eda_code_blocks(file_path, output_dir, comments)
    
    executed_blocks = []
    all_plot_urls = []
    
    try:
        for block in code_blocks:
            executed_block = execute_code_block(block, file_path, output_dir, max_retries)
            
            # Upload plots to Cloudinary if successful
            if executed_block.status == "success" and executed_block.plots_generated:
                uploaded = await upload_plots_from_block(
                    output_dir=output_dir,
                    plot_filenames=executed_block.plots_generated,
                    uid=uid,
                    csv_id=csv_id,
                    code_block_id=executed_block.id,
                    description=executed_block.description,
                    comment_id=comment_id
                )
                plot_urls = [p["cloudinary_url"] for p in uploaded]
                executed_block.plot_urls = plot_urls
                all_plot_urls.extend(plot_urls)
            
            executed_blocks.append(executed_block)
    finally:
        cleanup_temp_dir(output_dir)
    
    # Determine overall status
    if all(block.status == "success" for block in executed_blocks):
        overall_status = "completed"
    elif any(block.status == "error" for block in executed_blocks):
        overall_status = "partial_success"
    else:
        overall_status = "failed"
    
    return GenerateEDAResponse(
        csv_id=csv_id,
        csv_name=csv_name,
        total_blocks=len(executed_blocks),
        blocks=executed_blocks,
        overall_status=overall_status,
        plot_urls=all_plot_urls
    )


def generate_and_execute_eda_sync(file_path: str, output_dir: str, comments: Optional[str] = None, max_retries: int = 2) -> GenerateEDAResponse:
    """
    Generate and execute EDA code blocks synchronously.
    NOTE: This is the legacy version that doesn't upload to Cloudinary.
    """
    code_blocks = generate_eda_code_blocks(file_path, output_dir, comments)
    
    executed_blocks = []
    for block in code_blocks:
        executed_block = execute_code_block(block, file_path, output_dir, max_retries)
        executed_blocks.append(executed_block)
    
    # Determine overall status
    if all(block.status == "success" for block in executed_blocks):
        overall_status = "completed"
    elif any(block.status == "error" for block in executed_blocks):
        overall_status = "partial_success"
    else:
        overall_status = "failed"
    
    return GenerateEDAResponse(
        file_path=file_path,
        output_dir=output_dir,
        total_blocks=len(executed_blocks),
        blocks=executed_blocks,
        overall_status=overall_status
    )