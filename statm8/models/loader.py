from pydantic import BaseModel
from typing import Dict, List, Any, Optional

class ColumnInfo(BaseModel):
    name: str
    dtype: str
    non_null_count: int
    null_count: int
    unique_count: int
    sample_values: List[Any]

class DatasetSummaryResponse(BaseModel):
    csv_id: Optional[str] = None
    file_type: str
    total_rows: int
    total_columns: int
    columns_info: List[ColumnInfo]
    sample_rows: List[Dict[str, Any]]
    ai_summary: str