from fastapi import APIRouter, UploadFile, File, HTTPException
from statm8.services.loader import analyze_file
from statm8.models.loader import DatasetSummaryResponse

router = APIRouter(tags=["Data Loader"])

@router.post("/analyze", response_model=DatasetSummaryResponse)
async def analyze_dataset(file: UploadFile = File(...)):
    """
    Upload a CSV or JSON file and get a comprehensive dataset summary
    """
    if not file.filename.endswith(('.csv', '.json')):
        raise HTTPException(
            status_code=400, 
            detail="Only CSV and JSON files are supported"
        )
    
    try:
        content = await file.read()
        result = analyze_file(content, file.filename)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")