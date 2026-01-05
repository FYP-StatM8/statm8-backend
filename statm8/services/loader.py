import pandas as pd
import json
import os
import tempfile
from typing import Dict, List, Any
from statm8.models.loader import DatasetSummaryResponse, ColumnInfo
from statm8.constants.stat import llm, UPLOAD_FOLDER
from statm8.constants.loader import DATASET_SUMMARY_TEMPLATE

def serialize_value(value: Any) -> Any:
    """Convert numpy/pandas types to Python native types"""
    if pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp, pd.Period)):
        return str(value)
    if hasattr(value, 'item'):
        return value.item()
    return value

def load_dataframe(file_path: str) -> tuple[pd.DataFrame, str]:
    """Load CSV or JSON file into pandas DataFrame"""
    if file_path.endswith('.csv'):
        return pd.read_csv(file_path), 'csv'
    elif file_path.endswith('.json'):
        return pd.read_json(file_path), 'json'
    else:
        raise ValueError("Unsupported file type")

def get_column_info(df: pd.DataFrame) -> List[ColumnInfo]:
    """Extract detailed information about each column"""
    columns_info = []
    
    for col in df.columns:
        unique_values = df[col].dropna().unique()
        sample_values = [serialize_value(v) for v in unique_values[:5].tolist()]
        
        col_info = ColumnInfo(
            name=col,
            dtype=str(df[col].dtype),
            non_null_count=int(df[col].notna().sum()),
            null_count=int(df[col].isna().sum()),
            unique_count=int(df[col].nunique()),
            sample_values=sample_values
        )
        columns_info.append(col_info)
    
    return columns_info

def get_sample_rows(df: pd.DataFrame, n: int = 5) -> List[Dict[str, Any]]:
    """Get the first n rows as list of dictionaries"""
    sample_rows = []
    for _, row in df.head(n).iterrows():
        row_dict = {col: serialize_value(value) for col, value in row.items()}
        sample_rows.append(row_dict)
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

def save_file_to_folder(content: bytes, filename: str) -> str:
    """Save uploaded file to designated folder"""
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    with open(file_path, 'wb') as f:
        f.write(content)
    return file_path

def analyze_file(content: bytes, filename: str) -> DatasetSummaryResponse:
    """Complete dataset analysis pipeline"""

    file_path = save_file_to_folder(content, filename)
    
    # Load dataframe
    df, file_type = load_dataframe(file_path)

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