# api/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
# Import the router objects directly
from api.routes.gitdigest import router as gitdigest_router

app = FastAPI(title="GITHUB_SUMMARISER_API", version="1.0.0")

# CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include your routes with the router objects
app.include_router(gitdigest_router, prefix="/api/v1", tags=["GitDigest"])


@app.get("/api/v1/health")
async def health_check():
    return {"status": "healthy", "service": "GITHUB_SUMMARISER_API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="127.0.0.1", port=8001, reload=True)  # Using port 8001 to avoid conflict with any existing service on 8000