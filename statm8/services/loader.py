import pandas as pd
import json
import io
import tempfile
from typing import Dict, List, Any
from statm8.models.loader import DatasetSummaryResponse, ColumnInfo
from statm8.constants.stat import llm
from statm8.constants.loader import DATASET_SUMMARY_TEMPLATE

def serialize_value(value: Any) -> Any:
    """Convert numpy/pandas types to Python native types"""
    if pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp, pd.Period)):
        return str(value)
    if isinstance(value, (list, tuple, dict)):
        try:
            return json.dumps(value)
        except (TypeError, ValueError):
            return str(value)
    if hasattr(value, 'item'):
        try:
            return value.item()
        except (ValueError, OverflowError):
            return str(value)
    return value

def load_dataframe_from_bytes(content: bytes, filename: str) -> tuple[pd.DataFrame, str]:
    """Load CSV or JSON content into pandas DataFrame from bytes"""
    if filename.endswith('.csv'):
        return pd.read_csv(io.BytesIO(content)), 'csv'
    elif filename.endswith('.json'):
        try:
            data = json.loads(content.decode('utf-8'))
            
            if isinstance(data, list):
                if len(data) == 0:
                    raise ValueError("JSON file contains empty array")
                if isinstance(data[0], dict):
                    df = pd.DataFrame(data)
                    if df.empty:
                        raise ValueError("Failed to parse JSON: empty DataFrame")
                    return df, 'json'
                else:
                    raise ValueError("JSON array must contain objects/dictionaries")
            
            elif isinstance(data, dict):
                if all(isinstance(v, list) for v in data.values()):
                    lengths = [len(v) for v in data.values()]
                    if len(set(lengths)) > 1:
                        raise ValueError(f"All arrays must be of the same length. Found lengths: {set(lengths)}")
                    df = pd.DataFrame(data)
                    if df.empty:
                        raise ValueError("Failed to parse JSON: empty DataFrame")
                    return df, 'json'
                else:
                    df = pd.json_normalize([data])
                    if df.empty:
                        raise ValueError("Failed to parse JSON: empty DataFrame")
                    return df, 'json'
            else:
                raise ValueError(f"Unsupported JSON structure: {type(data)}")
                
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format: {str(e)}")
        except Exception as e:
            raise ValueError(f"Failed to load JSON file: {str(e)}")
    else:
        raise ValueError("Unsupported file type. Only CSV and JSON files are supported.")


def load_dataframe(file_path: str) -> tuple[pd.DataFrame, str]:
    """Load CSV or JSON file into pandas DataFrame (legacy - for temporary files)"""
    with open(file_path, 'rb') as f:
        content = f.read()
    filename = file_path.split('/')[-1]
    return load_dataframe_from_bytes(content, filename)

def get_column_info(df: pd.DataFrame) -> List[ColumnInfo]:
    """Extract detailed information about each column"""
    columns_info = []
    
    for col in df.columns:
        try:
            sample_values = []
            non_null_data = df[col].dropna()
            if len(non_null_data) > 0:
                unique_vals = []
                for idx in range(min(5, len(non_null_data))):
                    val = non_null_data.iloc[idx]
                    serialized = serialize_value(val)
                    if serialized is not None:
                        sample_values.append(serialized)
        except Exception as e:
            try:
                sample_values = [str(df[col].iloc[0])] if len(df) > 0 and pd.notna(df[col].iloc[0]) else []
            except:
                sample_values = []
        
        try:
            col_info = ColumnInfo(
                name=str(col),
                dtype=str(df[col].dtype),
                non_null_count=int(df[col].notna().sum()),
                null_count=int(df[col].isna().sum()),
                unique_count=int(df[col].nunique()),
                sample_values=sample_values[:5]
            )
            columns_info.append(col_info)
        except Exception as e:
            col_info = ColumnInfo(
                name=str(col),
                dtype="unknown",
                non_null_count=0,
                null_count=len(df),
                unique_count=0,
                sample_values=[]
            )
            columns_info.append(col_info)
    
    return columns_info

def get_sample_rows(df: pd.DataFrame, n: int = 5) -> List[Dict[str, Any]]:
    """Get the first n rows as list of dictionaries"""
    sample_rows = []
    try:
        for idx in range(min(n, len(df))):
            row = df.iloc[idx]
            row_dict = {}
            for col in df.columns:
                try:
                    value = row[col]
                    serialized = serialize_value(value)
                    row_dict[str(col)] = serialized if serialized is not None else None
                except Exception as e:
                    row_dict[str(col)] = None
            sample_rows.append(row_dict)
    except Exception as e:
        print(f"Error getting sample rows: {e}")
        sample_rows = []
    return sample_rows

def create_demographics(df: pd.DataFrame, file_type: str) -> str:
    """Create textual summary of dataset demographics"""
    demographics = f"""
Dataset Overview:
- Total Rows: {len(df)}
- Total Columns: {len(df.columns)}
- File Type: {file_type.upper()}

Column Details:
"""
    for col in df.columns:
        demographics += f"\n{col}:"
        demographics += f"\n  - Type: {df[col].dtype}"
        demographics += f"\n  - Non-null: {df[col].notna().sum()}"
        demographics += f"\n  - Null: {df[col].isna().sum()}"
        demographics += f"\n  - Unique values: {df[col].nunique()}"
        
        if pd.api.types.is_numeric_dtype(df[col]):
            demographics += f"\n  - Min: {df[col].min()}"
            demographics += f"\n  - Max: {df[col].max()}"
            demographics += f"\n  - Mean: {df[col].mean():.2f}"
    
    return demographics

def generate_ai_summary(demographics: str, sample_rows: List[Dict[str, Any]]) -> str:
    """Generate AI summary using LangChain"""
    sample_rows_str = json.dumps(sample_rows, indent=2)
    chain = DATASET_SUMMARY_TEMPLATE | llm
    response = chain.invoke({
        "demographics": demographics,
        "sample_rows": sample_rows_str
    })
    return response.content


def save_temp_file(content: bytes, filename: str) -> str:
    """Save uploaded file to a temporary location for processing"""
    temp_dir = tempfile.mkdtemp(prefix="statm8_upload_")
    file_path = f"{temp_dir}/{filename}"
    with open(file_path, 'wb') as f:
        f.write(content)
    return file_path


def cleanup_temp_file(file_path: str):
    """Clean up temporary file after processing"""
    import shutil
    try:
        temp_dir = '/'.join(file_path.split('/')[:-1])
        if temp_dir and temp_dir.startswith(tempfile.gettempdir()):
            shutil.rmtree(temp_dir)
    except Exception as e:
        print(f"Failed to cleanup temp file: {e}")


def analyze_file(content: bytes, filename: str) -> DatasetSummaryResponse:
    """
    Complete dataset analysis pipeline.
    Returns analysis results - storage is handled by the caller.
    """
    # Load dataframe directly from bytes
    df, file_type = load_dataframe_from_bytes(content, filename)

    columns_info = get_column_info(df)
    sample_rows = get_sample_rows(df, 5)
    demographics = create_demographics(df, file_type)
    
    ai_summary = generate_ai_summary(demographics, sample_rows)
    
    response = DatasetSummaryResponse(
        file_type=file_type,
        total_rows=len(df),
        total_columns=len(df.columns),
        columns_info=columns_info,
        sample_rows=sample_rows,
        ai_summary=ai_summary
    )
    
    return response