# backend/api/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
# Import the router objects directly
from api.routes.chat import router as chat_router
from api.routes.sessions import router as sessions_router
from api.routes.auth import router as auth_router

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
app.include_router(chat_router, prefix="/api/v1", tags=["GET"])


@app.get("/api/v1/health")
async def health_check():
    return {"status": "healthy", "service": "GITHUB_SUMMARISER_API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="127.0.0.1", port=8001, reload=True)  # Using port 8001 to avoid conflict with any existing service on 8000