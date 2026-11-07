# CourseMate AI — Project Context

## 1. Project Overview
CourseMate AI is an AI-powered personalized learning assistant.
Students can upload course materials, ask questions, generate
summaries and quizzes, and track their learning progress.

## 2. Technology Stack

### Frontend
- React
- Vite
- Tailwind CSS
- React Router
- Axios

### Backend
- Python
- FastAPI
- JWT Authentication

### Database
- MongoDB Atlas: application data
- ChromaDB: vector storage

### RAG and AI
- PyMuPDF: PDF text extraction
- Python: text cleaning and chunking
- Sentence Transformers: embeddings
- ChromaDB: semantic retrieval
- Groq API: primary LLM
- Gemini API: fallback LLM

## 3. Core Features
1. User authentication
2. Course creation and management
3. PDF upload and processing
4. RAG-based question answering
5. Answers with document and page citations
6. Chapter summaries
7. AI-generated quizzes
8. Flashcards
9. Topic-wise performance tracking
10. Personalized study recommendations

## 4. RAG Workflow

Document ingestion:
PDF -> Text Extraction -> Cleaning -> Chunking ->
Metadata -> Embeddings -> ChromaDB

Question answering:
Question -> Embedding -> Retrieval ->
Relevant Context -> LLM -> Grounded Answer + Citations

Each document chunk should preserve:
- user_id
- course_id
- document_id
- page_number
- chunk_id

## 5. Development Rules
- Build one module at a time.
- Reuse existing code wherever possible.
- Keep frontend and backend responsibilities separate.
- Write modular, maintainable code.
- Never hardcode API keys or secrets.
- Use environment variables for configuration.
- Validate inputs and handle errors.
- Implement user-level data isolation.
- Test each feature before moving forward.
- Avoid unnecessary dependencies.
- Do not claim a feature works until it has been tested.

## 6. Project Roadmap
1. Project foundation
2. Authentication
3. Course management
4. RAG document ingestion
5. RAG question answering
6. AI learning features
7. Knowledge tracking
8. Frontend integration
9. Testing and deployment

## 7. Current Progress
- Ubuntu development environment configured.
- React + Vite frontend created.
- FastAPI backend created.
- Python virtual environment created.
- Backend dependencies installed.
- FastAPI Swagger documentation working.
- GitHub repository initialized.

## 8. Important Development Constraint
Claude Free is used as a coding assistant only.
The deployed application uses Groq and Gemini APIs.
Do not introduce Claude API dependencies.
