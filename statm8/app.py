from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from statm8.endpoints import loader, generator, storage
import traceback

app = FastAPI(title="StatM8 API", version="1.0.0")

origins = [
    "http://localhost:8080",
    "http://localhost:3000",
    "http://127.0.0.1:8080",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(loader.router)
app.include_router(generator.router)
app.include_router(storage.router)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "detail": str(exc),
            "type": type(exc).__name__,
        },
        headers={
            "Access-Control-Allow-Origin": request.headers.get("origin", "http://localhost:8080"),
            "Access-Control-Allow-Credentials": "true",
        }
    )

@app.get("/")
def root():
    return {"message": "Welcome to Statm8 API"}

@app.get("/health")
def health_check():
    return {"status": "healthy", "message": "API is running"}