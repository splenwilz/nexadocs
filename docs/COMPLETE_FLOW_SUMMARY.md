# Complete System Flow Summary

This document provides a comprehensive overview of all user flows in the multi-tenant AI knowledge assistant system.

---

## 🎯 Three Main User Flows

### 1. **System Admin Flow** (Initial Setup)
### 2. **Company Founder Flow** (Self-Serve Signup)
### 3. **Team Member Flow** (Join Existing Tenant)

---

## Flow 1: System Admin Setup (One-Time Bootstrap)

### Purpose
Set up the first admin user who can provision tenants for other companies.

### Steps

```
1. Create Admin User in WorkOS Dashboard
   → Go to WorkOS Dashboard → User Management
   → Create user: admin@system.com
   → Set user metadata: role: "admin" OR add to organization with admin role

2. Create Admin Organization (Optional)
   → Create organization in WorkOS Dashboard
   → Add admin user with "admin" role

3. Admin Signs Up via API
   POST /api/v1/auth/signup
   {
     "email": "admin@system.com",
     "password": "SecurePass123!",
     "organization_id": "org_admin_123"  // From WorkOS Dashboard
   }

4. Admin Can Now Provision Tenants
   POST /api/v1/tenants/provision (Admin only)
   {
     "name": "Client Company",
     "domains": ["client.com"]
   }
   → Creates WorkOS org + tenant
   → Admin automatically added to org with admin role
```

**Result**: System admin can manage all tenants and provision new ones.

---

## Flow 2: Company Founder (Self-Serve Signup) ⭐ NEW

### Purpose
Allow new companies to sign up and create their own tenant without manual admin intervention.

### Complete Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: Founder Signs Up                                        │
└─────────────────────────────────────────────────────────────────┘
   POST /api/v1/auth/signup
   {
     "email": "founder@newcompany.com",
     "password": "SecurePass123!",
     "confirm_password": "SecurePass123!",
     "first_name": "John",
     "last_name": "Founder",
     "create_tenant": true,              ← Key: Self-serve flag
     "company_name": "New Company Inc",
     "company_domains": ["newcompany.com"]
   }

   System Automatically:
   ├─ ✅ Creates WorkOS Organization
   ├─ ✅ Creates Tenant in Database
   ├─ ✅ Creates WorkOS User
   ├─ ✅ Adds User to Organization with "admin" role
   └─ ✅ Creates Local User Record

   Response:
   {
     "user": { ... },
     "message": "User created successfully. Please verify your email to login."
   }

┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: Founder Verifies Email                                  │
└─────────────────────────────────────────────────────────────────┘
   Founder receives verification email with code

   POST /api/v1/auth/verify-email
   {
     "pending_authentication_token": "...",
     "code": "869622"  // From email
   }

   Response:
   {
     "access_token": "...",
     "refresh_token": "...",
     "user": {
       "email_verified": true,
       ...
     },
     "organization_id": "org_01KB51BXCPQA5WSHNN7G99EMX3",
     "role": "admin"  ← Founder is admin!
   }

┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: Founder Logs In                                          │
└─────────────────────────────────────────────────────────────────┘
   POST /api/v1/auth/signin
   {
     "email": "founder@newcompany.com",
     "password": "SecurePass123!"
   }

   Response:
   {
     "access_token": "...",
     "organization_id": "org_01KB51BXCPQA5WSHNN7G99EMX3",
     "user": { "role": "admin" }
   }

┌─────────────────────────────────────────────────────────────────┐
│ STEP 4: Founder Can Now Use System                               │
└─────────────────────────────────────────────────────────────────┘
   Founder (as admin) can:
   ├─ ✅ Upload documents for their company
   ├─ ✅ Chat with AI assistant (using their documents)
   ├─ ✅ View conversations
   ├─ ✅ Invite team members (share organization_id)
   └─ ✅ Manage their tenant
```

**Key Points**:
- ✅ **No manual admin steps required**
- ✅ **Fully automated tenant creation**
- ✅ **Founder automatically becomes admin**
- ✅ **Scalable for many companies**

---

## Flow 3: Team Member (Join Existing Tenant)

### Purpose
Allow team members to join a company that already has a tenant.

### Complete Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: Founder Shares Organization ID                          │
└─────────────────────────────────────────────────────────────────┘
   Founder shares: "org_01KB51BXCPQA5WSHNN7G99EMX3"
   (Can be shared via email, invite link, etc.)

┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: Team Member Signs Up                                     │
└─────────────────────────────────────────────────────────────────┘
   POST /api/v1/auth/signup
   {
     "email": "teammate@newcompany.com",
     "password": "SecurePass123!",
     "confirm_password": "SecurePass123!",
     "first_name": "Jane",
     "last_name": "Team",
     "organization_id": "org_01KB51BXCPQA5WSHNN7G99EMX3"  ← From founder
   }

   System Automatically:
   ├─ ✅ Creates WorkOS User
   ├─ ✅ Adds User to Existing Organization
   ├─ ✅ Resolves Tenant by Organization ID
   └─ ✅ Creates Local User Record (linked to same tenant)

   Response:
   {
     "user": { ... },
     "message": "User created successfully. Please verify your email to login."
   }

┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: Team Member Verifies Email                               │
└─────────────────────────────────────────────────────────────────┘
   POST /api/v1/auth/verify-email
   {
     "pending_authentication_token": "...",
     "code": "123456"  // From email
   }

┌─────────────────────────────────────────────────────────────────┐
│ STEP 4: Team Member Logs In                                      │
└─────────────────────────────────────────────────────────────────┘
   POST /api/v1/auth/signin
   {
     "email": "teammate@newcompany.com",
     "password": "SecurePass123!"
   }

   Response:
   {
     "access_token": "...",
     "organization_id": "org_01KB51BXCPQA5WSHNN7G99EMX3",  ← Same org as founder
     "user": { "role": "member" }  ← Team member (not admin)
   }

┌─────────────────────────────────────────────────────────────────┐
│ STEP 5: Team Member Can Use System                              │
└─────────────────────────────────────────────────────────────────┘
   Team Member can:
   ├─ ✅ Upload documents (shared with company)
   ├─ ✅ Chat with AI assistant (using company documents)
   ├─ ✅ View conversations
   └─ ❌ Cannot manage tenant (not admin)
```

**Key Points**:
- ✅ **Team members join existing tenant**
- ✅ **All data is shared within the tenant**
- ✅ **Team members get "member" role (not admin)**
- ✅ **Strict tenant isolation maintained**

---

## Flow Comparison Matrix

| Feature | System Admin | Company Founder | Team Member |
|---------|-------------|-----------------|-------------|
| **How Created** | WorkOS Dashboard | Self-serve signup | Signup with org_id |
| **Tenant Creation** | Can provision tenants | Creates own tenant | Joins existing tenant |
| **Role** | Admin (system-wide) | Admin (tenant-level) | Member |
| **Can Manage Tenants** | ✅ Yes (all tenants) | ✅ Yes (own tenant) | ❌ No |
| **Can Upload Documents** | ✅ Yes | ✅ Yes | ✅ Yes |
| **Can Chat** | ✅ Yes | ✅ Yes | ✅ Yes |
| **Data Access** | All tenants | Own tenant only | Own tenant only |

---

## Complete End-to-End Example

### Scenario: New Company "Acme Corp" Onboards

```
Day 1: Founder Self-Serves
─────────────────────────
1. Founder: POST /api/v1/auth/signup
   {
     "email": "founder@acme.com",
     "create_tenant": true,
     "company_name": "Acme Corp"
   }
   → Tenant created: "acme-corp"
   → Organization: org_acme_123
   → Founder is admin

2. Founder: Verifies email
   → Email verified

3. Founder: Logs in
   → Gets access token with admin role

4. Founder: Uploads documents
   POST /api/v1/documents/upload
   → Documents processed and indexed

5. Founder: Chats with AI
   POST /api/v1/chat
   → AI answers using Acme Corp documents

Day 2: Team Members Join
─────────────────────────
1. Founder shares: org_acme_123

2. Team Member 1: POST /api/v1/auth/signup
   {
     "email": "dev@acme.com",
     "organization_id": "org_acme_123"
   }
   → Joins Acme Corp tenant

3. Team Member 2: POST /api/v1/auth/signup
   {
     "email": "sales@acme.com",
     "organization_id": "org_acme_123"
   }
   → Joins Acme Corp tenant

4. All team members can:
   - Upload documents (shared)
   - Chat with AI (using shared documents)
   - View conversations (shared)
```

---

## API Endpoints Summary

### Authentication
- `POST /api/v1/auth/signup` - Sign up (supports self-serve tenant creation)
- `POST /api/v1/auth/signin` - Sign in
- `POST /api/v1/auth/verify-email` - Verify email
- `POST /api/v1/auth/refresh-token` - Refresh access token

### Tenant Management (Admin Only)
- `POST /api/v1/tenants/provision` - Provision tenant with WorkOS org
- `GET /api/v1/tenants` - List all tenants
- `GET /api/v1/tenants/{id}` - Get tenant details
- `PATCH /api/v1/tenants/{id}` - Update tenant
- `DELETE /api/v1/tenants/{id}` - Delete tenant

### Documents (Tenant-Scoped)
- `POST /api/v1/documents/upload` - Upload document
- `GET /api/v1/documents` - List documents (tenant-scoped)
- `GET /api/v1/documents/{id}` - Get document details
- `DELETE /api/v1/documents/{id}` - Delete document

### Chat (Tenant-Scoped)
- `POST /api/v1/chat` - Send chat message
- `GET /api/v1/conversations` - List conversations (tenant-scoped)
- `GET /api/v1/conversations/{id}` - Get conversation details

---

## Key Design Decisions

### 1. **Self-Serve vs Admin-Provisioned**
- **Self-Serve**: Companies can create their own tenant (Flow 2)
- **Admin-Provisioned**: System admin can provision tenants (Flow 1)
- **Both work**: System supports both approaches

### 2. **Role Assignment**
- **First user in tenant**: Automatically gets `admin` role
- **Subsequent users**: Get `member` role
- **System admin**: Has admin role in their own organization

### 3. **Tenant Isolation**
- All data is strictly isolated per tenant
- Users can only access their tenant's data
- Vector embeddings stored in tenant-specific collections

### 4. **Email Verification**
- Required for all users before login
- Prevents fake account creation
- Standard security practice

---

## Summary

✅ **Three distinct flows** for different user types:
1. **System Admin**: Bootstrap and manage tenants
2. **Company Founder**: Self-serve tenant creation
3. **Team Member**: Join existing tenant

✅ **Fully automated** where possible:
- Self-serve tenant creation
- Automatic role assignment
- Automatic tenant linking

✅ **Scalable** for production:
- No manual steps for new companies
- Supports unlimited tenants
- Strict data isolation

✅ **Secure**:
- Email verification required
- Role-based access control
- Tenant isolation enforced

