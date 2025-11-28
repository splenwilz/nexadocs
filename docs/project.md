We are building a multi-tenant AI knowledge assistant that allows each client (tenant) to upload their own documents (PDF manuals, SOPs, contracts, production guides, etc.), ask questions, and receive answers based only on their own document set.

The system must isolate knowledge per client, provide a chat interface, support document ingestion + embeddings per tenant, and include an admin interface for reviewing and correcting answers.

Scope / Requirements (MVP)

Web App
	•	Multi-tenant architecture (strict separation)
	•	Login system (email + password per tenant user)
	•	Create tenant / delete tenant
	•	Upload PDF files per tenant
	•	Simple dashboard per tenant to see uploaded files

AI / RAG Pipeline
	•	PDF → text extraction (OCR if needed)
	•	Chunking & embeddings per tenant
	•	Vector DB separation per tenant (Qdrant / Pinecone / Weaviate)
	•	Retrieval logic: detect tenant + search only inside tenant index
	•	LLM response based strictly on retrieved content
	•	Show citations (document name + page/section)

Chat UI
	•	Chat interface per tenant (web-based)
	•	Tenant user can ask natural language questions
	•	Response references only their documents

Admin Panel
	•	View all conversations per tenant
	•	See Q&A logs
	•	Correct an answer & save it as validated answer example
	•	Simple UI to manage tenants and users

User & Tenant Management
	•	Admin can create tenant
	•	Admin can create tenant user
	•	Admin can delete tenant (remove all data + embeddings)

⸻

Tech Stack Preferences
	•	Backend: Python + FastAPI
	•	Frontend: Next.js or lightweight HTML/JS
	•	Vector DB: Qdrant / Pinecone
	•	Database: Postgres or SQLite
	•	LLM: OpenAI / Anthropic
	•	Deployment: VPS or small cloud instance

⸻

Deliverables
	•	Fully working MVP
	•	Deployed version on test environment
	•	Source code + documentation
	•	Short architecture documentation

⸻

Success Criteria
	•	Create 3 tenants (example: tenantA / tenantB / tenantC)
	•	Upload 20–30 PDF files per tenant
	•	Ask question → system answers only from that tenant’s documents with citations
	•	Admin can correct and store validated answers
	•	Delete tenant removes all related files + vectors successfully