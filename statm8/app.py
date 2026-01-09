from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from statm8.endpoints import loader, generator, storage

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)

app.include_router(loader.router)
app.include_router(generator.router)
app.include_router(storage.router)

@app.get("/")
def root():
    return {"message": "Welcome to Statm8 API"}