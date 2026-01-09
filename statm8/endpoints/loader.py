from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from statm8.services.loader import analyze_file
from statm8.models.loader import DatasetSummaryResponse
from statm8.constants.stat import UPLOAD_FOLDER
from statm8.services.storage import upload_csv_file
import os
import json

router = APIRouter(tags=["Data Loader"])

@router.post("/load", response_model=DatasetSummaryResponse)
async def analyze_dataset(
    uid: str = Form(...),
    file: UploadFile = File(...)
):
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

        base_name = os.path.splitext(file.filename)[0]
        output_path = os.path.join(UPLOAD_FOLDER, f"{base_name}.json")

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result.dict(), f, indent=2, ensure_ascii=False)

        # reset pointer before reusing file
        file.file.seek(0)

        # Call helper to upload & store in MongoDB
        result_dict = result.model_dump()
        upload_response = await upload_csv_file(
            uid=uid,
            csv_name=base_name,
            json_response=json.dumps(result_dict, ensure_ascii=False),
            csv_file=file
        )
        print(upload_response)
        result.csv_id = upload_response['csv_id']
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")