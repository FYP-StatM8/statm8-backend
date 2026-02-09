from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from statm8.services.loader import analyze_file
from statm8.models.loader import DatasetSummaryResponse
from statm8.services.storage import upload_csv_file
import json

router = APIRouter(tags=["Data Loader"])

@router.post("/load", response_model=DatasetSummaryResponse)
async def analyze_dataset(
    uid: str = Form(...),
    file: UploadFile = File(...)
):
    """
    Upload a CSV or JSON file and get a comprehensive dataset summary.
    File is stored in MongoDB and Cloudinary (no local storage).
    """
    if not file.filename.endswith(('.csv', '.json')):
        raise HTTPException(
            status_code=400, 
            detail="Only CSV and JSON files are supported"
        )
    
    try:
        content = await file.read()
        result = analyze_file(content, file.filename)

        # Reset pointer before reusing file
        file.file.seek(0)
        
        # Upload to MongoDB/Cloudinary (required)
        result_dict = result.model_dump()
        upload_response = await upload_csv_file(
            uid=uid,
            csv_name=file.filename.rsplit('.', 1)[0],
            json_response=json.dumps(result_dict, ensure_ascii=False),
            csv_file=file
        )
        result.csv_id = upload_response.get('csv_id')
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error processing file: {error_trace}")
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")