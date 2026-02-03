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

        # Try to upload to MongoDB/Cloudinary if available, but don't fail if unavailable
        try:
            # reset pointer before reusing file
            file.file.seek(0)
            
            result_dict = result.model_dump()
            upload_response = await upload_csv_file(
                uid=uid,
                csv_name=base_name,
                json_response=json.dumps(result_dict, ensure_ascii=False),
                csv_file=file
            )
            result.csv_id = upload_response.get('csv_id', 'local_only')
            print(f"File uploaded successfully to database: {result.csv_id}")
        except HTTPException as e:
            if e.status_code == 503:
                print("Database/Cloudinary unavailable. File saved locally only.")
                import hashlib
                import time
                unique_id = hashlib.md5(f"{base_name}_{uid}_{time.time()}".encode()).hexdigest()[:8]
                result.csv_id = f"local_{unique_id}"
            else:
                raise
        except Exception as e:
            print(f"Failed to upload to cloud storage: {e}. File saved locally only.")
            import hashlib
            import time
            unique_id = hashlib.md5(f"{base_name}_{uid}_{time.time()}".encode()).hexdigest()[:8]
            result.csv_id = f"local_{unique_id}"
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error processing file: {error_trace}")
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")