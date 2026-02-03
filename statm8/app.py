from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from statm8.endpoints import loader, generator, vlm, export

app = FastAPI(
    title="Statm8 API",
    description="Automated EDA with AI-powered analysis and export capabilities",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)

app.include_router(loader.router)
app.include_router(generator.router)
app.include_router(vlm.router)
app.include_router(export.router)

@app.get("/")
def root():
    return {"message": "Welcome to Statm8 API"}