import os
from dotenv import load_dotenv
from fastapi import Header, HTTPException

load_dotenv()

SERVICE_KEY = os.getenv("STRAVBIKE_SERVICE_KEY")

async def verify_service_key(x_api_key: str = Header(None)):
    if not SERVICE_KEY:
        raise HTTPException(status_code=500, detail="STRAVBIKE_SERVICE_KEY not configured")
    if x_api_key != SERVICE_KEY:
        raise HTTPException(status_code=401, detail="Invalid service key")
