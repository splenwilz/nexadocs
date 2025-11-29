# NexaDocs - Multi-Tenant AI Knowledge Assistant

A multi-tenant AI knowledge assistant that allows each client (tenant) to upload their own documents, ask questions, and receive AI-powered answers based strictly on their own document set.

NexaDocs is a **multi-tenant AI knowledge assistant** that provides:

- **Document Management**: Each tenant can upload PDF documents (manuals, SOPs, contracts, guides, etc.)
- **AI-Powered Chat**: Natural language Q&A interface that answers questions using only the tenant's own documents
- **RAG Pipeline**: Retrieval-Augmented Generation (RAG) with vector embeddings for semantic search
- **Strict Tenant Isolation**: Complete data separation - each tenant only sees their own documents and conversations
- **Self-Serve Onboarding**: Companies can sign up and create their own tenant automatically
- **Admin Management**: System admins can provision tenants, manage users, and review conversations

## Key Features

### Multi-Tenant Architecture
- ✅ **Strict Data Isolation**: All data (documents, conversations, embeddings) is isolated per tenant
- ✅ **Self-Serve Signup**: Companies can create their own tenant during signup
- ✅ **Admin Provisioning**: System admins can provision tenants with WorkOS organizations
- ✅ **Automatic Tenant Linking**: Users are automatically linked to tenants via WorkOS organizations

### Document Processing & RAG
- ✅ **PDF Text Extraction**: Extracts text from PDF documents
- ✅ **Intelligent Chunking**: Splits documents into contextually relevant chunks
- ✅ **Vector Embeddings**: Generates embeddings using OpenAI's embedding models
- ✅ **Vector Database**: Stores embeddings in Qdrant with tenant-isolated collections
- ✅ **Semantic Search**: Retrieves relevant document chunks based on user queries
- ✅ **LLM Responses**: Generates answers using OpenAI's chat models with retrieved context
- ✅ **Citations**: Shows which documents and sections were used to generate answers

### Authentication & Authorization
- ✅ **WorkOS Integration**: User authentication and organization management via WorkOS
- ✅ **Role-Based Access Control**: Admin and member roles with proper permissions
- ✅ **Email Verification**: Required before users can access the system
- ✅ **JWT Tokens**: Secure session management with role claims

### Storage & Infrastructure
- ✅ **S3 Storage**: All documents stored in Amazon S3 (no local storage)
- ✅ **PostgreSQL**: Relational database for metadata and user data
- ✅ **Qdrant**: Vector database for semantic search
- ✅ **Async Operations**: Fully asynchronous for optimal performance

### API Features
- ✅ **RESTful API**: Clean, well-documented REST API
- ✅ **OpenAPI/Swagger**: Auto-generated API documentation
- ✅ **Error Handling**: Comprehensive error handling with proper HTTP status codes
- ✅ **Performance Logging**: Detailed performance metrics for optimization

## How It Works

### User Flows

1. **Company Signs Up**:
   - Company signs up with `create_tenant=true` and company name
   - System automatically creates WorkOS organization and tenant
   - Company becomes admin of their tenant
   - No manual steps required

2. **Team Members Join**:
   - Team members sign up with the organization ID (from Company)
   - Automatically linked to the same tenant
   - Can upload documents and chat with AI

3. **Document Upload & Processing**:
   - User uploads PDF document
   - System extracts text, chunks it, generates embeddings
   - Stores chunks in PostgreSQL and embeddings in Qdrant
   - Document ready for AI queries

4. **AI Chat**:
   - User asks a question
   - System embeds the query, searches tenant's vector collection
   - Retrieves relevant document chunks
   - Generates answer using LLM with retrieved context
   - Returns answer with citations

### Architecture

```plaintext
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Backend                      │
├─────────────────────────────────────────────────────────┤
│  API Layer (Routes)                                      │
│  ├── Auth (signup, login, verify)                       │
│  ├── Documents (upload, list, delete)                   │
│  ├── Chat (send message, list conversations)            │
│  └── Tenants (provision, manage)                        │
├─────────────────────────────────────────────────────────┤
│  Service Layer (Business Logic)                          │
│  ├── Document Processing (PDF → text → chunks → vectors)│
│  ├── RAG Pipeline (query → search → generate)            │
│  ├── Tenant Management (provision, isolation)            │
│  └── Authentication (WorkOS integration)                 │
├─────────────────────────────────────────────────────────┤
│  Data Layer                                              │
│  ├── PostgreSQL (users, tenants, documents, chunks)     │
│  ├── Qdrant (vector embeddings per tenant)              │
│  └── S3 (document storage)                              │
└─────────────────────────────────────────────────────────┘
```

## Project Structure

```plaintext
nexadocs/
├── app/
│   ├── main.py                    # FastAPI application entry point
│   ├── api/v1/
│   │   ├── routes/
│   │   │   ├── auth.py           # Authentication endpoints
│   │   │   ├── document.py       # Document management
│   │   │   ├── chat.py           # Chat/conversation endpoints
│   │   │   └── tenant.py         # Tenant management (admin)
│   │   └── schemas/              # Pydantic request/response models
│   ├── core/
│   │   ├── config.py             # Application configuration
│   │   ├── database.py           # Database connection
│   │   ├── tenant.py              # Tenant context dependencies
│   │   ├── admin.py              # Admin authorization
│   │   └── storage/              # Storage backends (S3)
│   ├── models/                   # SQLAlchemy database models
│   │   ├── tenant.py
│   │   ├── user.py
│   │   ├── document.py
│   │   ├── document_chunk.py
│   │   └── conversation.py
│   └── services/                 # Business logic
│       ├── auth.py               # Authentication service
│       ├── tenant.py             # Tenant management
│       ├── document.py            # Document operations
│       ├── document_processor.py # Processing pipeline
│       ├── pdf_extractor.py      # PDF text extraction
│       ├── text_chunker.py      # Text chunking
│       ├── embeddings.py         # Embedding generation
│       ├── vector_db.py           # Qdrant operations
│       ├── rag.py                # RAG pipeline
│       └── chat.py               # Chat service
├── docs/                         # Documentation
│   ├── tenant_onboarding_flow.md
│   ├── self_serve_signup.md
│   ├── complete_flow_summary.md
│   ├── admin_user_setup.md
│   └── workos_jwt_template.md
├── alembic/                      # Database migrations
└── pyproject.toml                # Dependencies
```

## Tech Stack

- **Backend**: FastAPI (Python 3.12+)
- **Database**: PostgreSQL (async SQLAlchemy)
- **Vector DB**: Qdrant
- **Storage**: Amazon S3
- **Authentication**: WorkOS
- **AI/ML**: OpenAI (embeddings + chat completions)
- **Migrations**: Alembic
- **Package Manager**: uv

## Prerequisites

- Python 3.12+ (3.13 for local dev, 3.12 for Vercel deployment)
- [uv](https://github.com/astral-sh/uv) package manager
- PostgreSQL database (local or remote)

## Setup

### 1. Install Dependencies

Dependencies are managed with `uv`. They are automatically installed when you run commands with `uv run`.

### 2. Configure Environment Variables

**Important:** Copy the example environment file and configure your settings:

```bash
cp .env.example .env
```

Then edit `.env` with your configuration:

```bash
# Database Configuration
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/nexadocs

# WorkOS Configuration
WORKOS_API_KEY=sk_...
WORKOS_CLIENT_ID=client_...
WORKOS_ALLOWED_REDIRECT_URIS=http://localhost:3000/callback

# S3 Configuration
S3_BUCKET_NAME=your-bucket-name
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...

# OpenAI Configuration
OPENAI_API_KEY=sk-...
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSIONS=1536
OPENAI_CHAT_MODEL=gpt-4o-mini

# Qdrant Configuration
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=...  # Optional for Qdrant Cloud

# API Configuration
API_V1_PREFIX=/api/v1
PROJECT_NAME=NexaDocs
VERSION=0.1.0
```

**Note:** 
- The `.env` file is gitignored and should not be committed
- The application uses `asyncpg` for async operations, but Alembic uses `psycopg2` for migrations (sync driver)
- All sensitive configuration should be in `.env` file, not hardcoded

### 3. Initialize Database

First, ensure PostgreSQL is running and create the database:

```bash
createdb nexadocs
```

Or using PostgreSQL client:

```sql
CREATE DATABASE nexadocs;
```

### 4. Setup Qdrant (Vector Database)

#### Option A: Local Qdrant (Docker)
```bash
docker run -p 6333:6333 qdrant/qdrant
```

#### Option B: Qdrant Cloud
- Sign up at [https://cloud.qdrant.io](https://cloud.qdrant.io)
- Create a cluster and get your API key
- Set `QDRANT_URL` and `QDRANT_API_KEY` in `.env`

### 5. Run Migrations

Create your initial migration based on your database models:

```bash
# Create initial migration
uv run alembic revision --autogenerate -m "Initial migration"

# Apply migrations
uv run alembic upgrade head
```

## Running the Application

### Development Server

```bash
uv run uvicorn app.main:app --reload
```

The API will be available at:
- API: [http://localhost:8000](http://localhost:8000)
- Docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### API Documentation

Once the server is running, access the interactive API documentation:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### Quick Test

**1. Health Check**:
```bash
curl http://localhost:8000/api/v1/health
```

**2. Self-Serve Signup** (Company Founder):
```bash
curl -X POST http://localhost:8000/api/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "founder@company.com",
    "password": "SecurePass123!",
    "confirm_password": "SecurePass123!",
    "create_tenant": true,
    "company_name": "My Company"
  }'
```

**3. Upload Document** (after login):
```bash
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@document.pdf"
```

**4. Chat with AI** (after document processing):
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is this document about?"}'
```

## Development

### Adding New Routes

1. Create a new route file in `app/api/v1/routes/`
2. Import and include the router in `app/api/v1/api.py`

Example:
```python
# app/api/v1/routes/users.py
from fastapi import APIRouter

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/")
async def get_users():
    return {"users": []}
```

Then add to `app/api/v1/api.py`:
```python
from app.api.v1.routes import users
api_router.include_router(users.router)
```

### Adding Database Models

1. Create model in `app/models/`
2. Import in `app/models/__init__.py`
3. Import in `alembic/env.py` (for autogenerate)

Example:
```python
# app/models/user.py
from sqlalchemy import Column, Integer, String
from app.core.database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True)
```

### Creating Migrations

```bash
# Auto-generate migration from model changes
uv run alembic revision --autogenerate -m "Description of changes"

# Create empty migration
uv run alembic revision -m "Description of changes"
```

### Applying Migrations

```bash
# Apply all pending migrations
uv run alembic upgrade head

# Rollback one migration
uv run alembic downgrade -1

# Rollback to specific revision
uv run alembic downgrade <revision>
```

## Key Concepts

### Multi-Tenancy

Every user belongs to a **tenant** (company/organization). All data is strictly isolated:
- Documents are tenant-scoped
- Conversations are tenant-scoped
- Vector embeddings are stored in tenant-specific Qdrant collections
- Users can only access their tenant's data

### Tenant Onboarding

**Self-Serve Flow** (Recommended):
- Company founder signs up with `create_tenant=true`
- System automatically creates WorkOS organization and tenant
- Founder becomes admin automatically

**Admin-Provisioned Flow**:
- System admin provisions tenant via `POST /api/v1/tenants/provision`
- Admin shares organization ID with company
- Company members sign up with organization ID

### RAG Pipeline

1. **Document Upload**: PDF uploaded to S3
2. **Text Extraction**: Extract text from PDF
3. **Chunking**: Split text into manageable chunks (1000 chars, 200 overlap)
4. **Embedding**: Generate vector embeddings using OpenAI
5. **Storage**: Store chunks in PostgreSQL, embeddings in Qdrant
6. **Query**: User asks question → embed query → search Qdrant → retrieve chunks → generate answer

### Performance

- **Async Operations**: All I/O operations are asynchronous
- **Batch Processing**: Embeddings generated in batches
- **Optimized Prompts**: Concise system prompts for faster LLM responses
- **Context Truncation**: Limits context length to reduce token usage
- **Performance Logging**: Detailed timing metrics for optimization

## Documentation

- **[Tenant Onboarding Flow](docs/tenant_onboarding_flow.md)**: Complete tenant provisioning guide
- **[Self-Serve Signup](docs/self_serve_signup.md)**: Self-serve tenant creation documentation
- **[Complete Flow Summary](docs/complete_flow_summary.md)**: All user flows explained
- **[Admin Setup](docs/admin_user_setup.md)**: Admin user bootstrap guide

## Deployment

### Vercel Deployment

1. **Install Dev Dependencies Locally:**
   ```bash
   uv sync  # Installs all dependencies including dev
   ```

2. **Set Environment Variables in Vercel:**
   - Go to your project settings in Vercel
   - Add `DATABASE_URL` environment variable with your PostgreSQL connection string
   - Format: `postgresql+asyncpg://user:password@host:port/database`

3. **Deploy:**
   ```bash
   vercel --prod
   ```

**Note:** 
- Runtime dependencies don't include `psycopg2-binary` or `alembic` (only needed for local migrations)
- Python 3.12 is used (Vercel doesn't support 3.13 yet)
- Make sure to run migrations on your database before deploying

## API Endpoints

### Authentication
- `POST /api/v1/auth/signup` - Sign up (supports self-serve tenant creation)
- `POST /api/v1/auth/signin` - Sign in
- `POST /api/v1/auth/verify-email` - Verify email address

### Documents (Tenant-Scoped)
- `POST /api/v1/documents/upload` - Upload document
- `GET /api/v1/documents` - List documents
- `GET /api/v1/documents/{id}` - Get document details
- `DELETE /api/v1/documents/{id}` - Delete document

### Chat (Tenant-Scoped)
- `POST /api/v1/chat` - Send chat message
- `GET /api/v1/conversations` - List conversations
- `GET /api/v1/conversations/{id}` - Get conversation details

### Tenants (Admin Only)
- `POST /api/v1/tenants/provision` - Provision new tenant with WorkOS org
- `GET /api/v1/tenants` - List all tenants
- `GET /api/v1/tenants/{id}` - Get tenant details
- `PATCH /api/v1/tenants/{id}` - Update tenant
- `DELETE /api/v1/tenants/{id}` - Delete tenant

## References

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy Async Documentation](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [WorkOS Documentation](https://workos.com/docs)
- [OpenAI API Documentation](https://platform.openai.com/docs)
- [Qdrant Documentation](https://qdrant.tech/documentation/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [uv Documentation](https://github.com/astral-sh/uv)

## License

MIT

