from fastapi import FastAPI

app = FastAPI(
    title="CourseMate AI",
    description="AI-powered personalized learning assistant",
    version="1.0.0"
)

@app.get("/")
def home():
    return {
        "message": "Welcome to CourseMate AI!",
        "status": "running"
    }

@app.get("/health")
def health():
    return {"status": "healthy"}