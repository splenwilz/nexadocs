# Tenant Onboarding & User Signup Flow

This document describes the complete flow for tenant provisioning and user signup in the multi-tenant AI knowledge assistant system.

## Overview

The system supports **automated tenant provisioning** where admins can create tenants with WorkOS organizations in a single API call. Users then sign up with the WorkOS organization ID and are automatically linked to the provisioned tenant.

---

## Flow 1: Automated Tenant Provisioning (Admin-Driven)

### Step 1: Admin Provisions Tenant
**Endpoint**: `POST /api/v1/tenants/provision` (Admin only)

**Request**:
```json
{
  "name": "Acme Corporation",
  "domains": ["acme.com"]  // Optional
}
```

**What Happens**:
1. ✅ **WorkOS Organization Created**: 
   - Creates a new WorkOS organization via WorkOS API
   - Associates optional domains (in `pending` state)
   - Returns WorkOS organization ID (e.g., `org_01KB506QM707PJ6J82YZH618TN`)

2. ✅ **Tenant Record Created**:
   - Creates tenant in PostgreSQL database
   - Auto-generates unique slug from name (e.g., `"Acme Corporation"` → `"acme-corporation"`)
   - Links tenant to WorkOS organization via `workos_organization_id`
   - Sets `is_active = true`

3. ✅ **Admin Automatically Added**:
   - Creates organization membership for the admin user
   - Assigns `admin` role to the admin in the new organization
   - Admin can now access and manage the provisioned tenant

**Response**:
```json
{
  "id": "15d58d0f-1d94-4682-922e-af9a47de1beb",
  "name": "Acme Corporation",
  "slug": "acme-corporation",
  "workos_organization_id": "org_01KB506QM707PJ6J82YZH618TN",
  "is_active": true,
  "created_at": "2025-11-28T10:30:09.070986Z",
  "updated_at": "2025-11-28T10:30:09.070986Z"
}
```

**Key Points**:
- ✅ No manual WorkOS organization creation needed
- ✅ No need to copy/paste organization IDs
- ✅ Slug is auto-generated (no conflicts)
- ✅ Domains are optional (can be added later)
- ✅ Admin is automatically added to the provisioned organization with admin role

---

## Flow 2A: Self-Serve Tenant Creation (New Companies)

### Step 1: Company Founder Signs Up
**Endpoint**: `POST /api/v1/auth/signup` (Public)

**Field Requirements**:
- ✅ `create_tenant`: **MUST be `true`**
- ✅ `company_name`: **REQUIRED** - Company/tenant name
- ❌ `organization_id`: **MUST NOT be provided** (doesn't exist yet)
- ⚪ `company_domains`: Optional - Email domains

**Request**:
```json
{
  "email": "founder@newcompany.com",
  "password": "SecurePass123!",
  "confirm_password": "SecurePass123!",
  "first_name": "John",
  "last_name": "Founder",
  "create_tenant": true,              ← Required: Must be true
  "company_name": "New Company Inc",  ← Required: Company name
  "company_domains": ["newcompany.com"]  ← Optional: Email domains
  // organization_id: NOT PROVIDED ← Must not be included
}
```

**What Happens**:
1. ✅ **WorkOS Organization Created**: 
   - Creates new WorkOS organization with company name
   - Associates optional domains (in `pending` state)

2. ✅ **Tenant Record Created**:
   - Creates tenant in PostgreSQL database
   - Auto-generates unique slug from company name
   - Links tenant to WorkOS organization

3. ✅ **WorkOS User Created**:
   - Creates user in WorkOS User Management

4. ✅ **User Added to Organization with Admin Role**:
   - Creates organization membership
   - Assigns `admin` role to the first user
   - First user becomes admin of their own tenant

5. ✅ **Local User Record Created**:
   - Creates user in PostgreSQL database
   - Links user to the newly created tenant

**Response**:
```json
{
  "user": {
    "id": "user_01KB51CBQMWPGPBYJ4014145JV",
    "email": "founder@newcompany.com",
    ...
  },
  "message": "User created successfully. Please verify your email to login."
}
```

**Key Points**:
- ✅ No manual admin steps required
- ✅ Founder automatically becomes admin
- ✅ Fully automated tenant creation
- ✅ Scalable for many companies

---

## Flow 2B: User Signup (Join Existing Tenant)

### Step 1: User Signs Up
**Endpoint**: `POST /api/v1/auth/signup` (Public)

**Field Requirements**:
- ✅ `organization_id`: **REQUIRED** - Get from founder/admin
- ❌ `create_tenant`: **MUST be `false` or omitted** (defaults to false)
- ❌ `company_name`: **MUST NOT be provided** (not needed)

**Request**:
```json
{
  "email": "john@acme.com",
  "password": "SecurePass123!",
  "confirm_password": "SecurePass123!",
  "first_name": "John",
  "last_name": "Doe",
  "organization_id": "org_01KB506QM707PJ6J82YZH618TN"  ← Required: From founder/admin
  // create_tenant: NOT PROVIDED (defaults to false)
  // company_name: NOT PROVIDED
}
```

**What Happens**:

1. ✅ **Check if user exists**:
   - If user already exists in database → Return error (409 Conflict)

2. ✅ **Create WorkOS User**:
   - Creates user in WorkOS User Management
   - Returns WorkOS user object

3. ✅ **Create WorkOS Organization Membership**:
   - Adds user to the specified WorkOS organization
   - Links user to organization via organization membership
   - If this fails → Clean up WorkOS user

4. ✅ **Resolve Tenant** (Key Step):
   - Calls `get_or_create_tenant_by_workos_organization_id(organization_id)`
   - **If tenant exists** (provisioned via Flow 1):
     - ✅ Finds tenant by `workos_organization_id`
     - ✅ Returns existing tenant
   - **If tenant doesn't exist** (legacy/fallback):
     - ✅ Creates new tenant with auto-generated slug
     - ✅ Sets `workos_organization_id` to the provided organization ID
     - ⚠️ This is a fallback for organizations created outside our system

5. ✅ **Create Local User Record**:
   - Creates user in PostgreSQL database
   - Sets `tenant_id` to the resolved tenant's ID
   - Links user to tenant for data isolation

**Response**:
```json
{
  "user": {
    "id": "user_01KA8NT9K4C9PC87T4TMCWVF70",
    "email": "john@acme.com",
    "first_name": "John",
    "last_name": "Doe",
    ...
  }
}
```

**Key Points**:
- ✅ Users are automatically linked to the correct tenant
- ✅ If tenant was provisioned (Flow 1), user joins existing tenant
- ✅ If tenant doesn't exist, it's created automatically (fallback)
- ✅ All data (documents, conversations) is isolated per tenant

---

## Complete End-to-End Flow

### Scenario: New Company Onboarding

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. ADMIN PROVISIONS TENANT                                      │
└─────────────────────────────────────────────────────────────────┘
   Admin → POST /api/v1/tenants/provision
           {
             "name": "Acme Corporation",
             "domains": ["acme.com"]
           }
   
   System:
   ├─ Creates WorkOS Organization → org_01KB506QM707PJ6J82YZH618TN
   ├─ Creates Tenant in DB
   │  ├─ name: "Acme Corporation"
   │  ├─ slug: "acme-corporation" (auto-generated)
   │  └─ workos_organization_id: "org_01KB506QM707PJ6J82YZH618TN"
   └─ Returns tenant with workos_organization_id

┌─────────────────────────────────────────────────────────────────┐
│ 2. ADMIN SHARES ORGANIZATION ID                                 │
└─────────────────────────────────────────────────────────────────┘
   Admin shares: "org_01KB506QM707PJ6J82YZH618TN"
   (Can be shared via email, invite link, etc.)

┌─────────────────────────────────────────────────────────────────┐
│ 3. USER SIGNS UP                                                │
└─────────────────────────────────────────────────────────────────┘
   User → POST /api/v1/auth/signup
          {
            "email": "john@acme.com",
            "password": "SecurePass123!",
            "organization_id": "org_01KB506QM707PJ6J82YZH618TN"
          }
   
   System:
   ├─ Creates WorkOS User
   ├─ Creates WorkOS Organization Membership
   ├─ Resolves Tenant:
   │  └─ Finds tenant by workos_organization_id ✅
   │     └─ Returns existing "Acme Corporation" tenant
   └─ Creates Local User with tenant_id linked

┌─────────────────────────────────────────────────────────────────┐
│ 4. USER CAN NOW ACCESS TENANT DATA                              │
└─────────────────────────────────────────────────────────────────┘
   User → GET /api/v1/documents
          (Returns only documents for "Acme Corporation" tenant)
   
   User → POST /api/v1/chat
          (Chat responses use only "Acme Corporation" documents)
```

---

## Comparison: Old vs New Flow

### ❌ Old Flow (Manual)
1. Admin manually creates WorkOS organization in WorkOS Dashboard
2. Admin copies organization ID
3. Admin creates tenant via `POST /api/v1/tenants` with manual slug
4. Admin shares organization ID with users
5. Users sign up with organization ID

**Problems**:
- ❌ Manual WorkOS organization creation
- ❌ Copy/paste errors
- ❌ No domain association during tenant creation
- ❌ Not scalable for production

### ✅ New Flow (Automated)
1. Admin provisions tenant via `POST /api/v1/tenants/provision`
   - ✅ WorkOS organization created automatically
   - ✅ Tenant created automatically
   - ✅ Slug auto-generated
   - ✅ Domains can be associated
2. Admin shares organization ID (from response)
3. Users sign up with organization ID
   - ✅ Automatically linked to provisioned tenant

**Benefits**:
- ✅ Fully automated
- ✅ No manual WorkOS dashboard steps
- ✅ Scalable for production
- ✅ Domain association supported
- ✅ Auto-generated slugs prevent conflicts

---

## Fallback Behavior

If a user signs up with an organization ID that **wasn't provisioned** through our system:

1. ✅ System creates tenant automatically via `get_or_create_tenant_by_workos_organization_id()`
2. ✅ Tenant gets auto-generated slug from organization name (or org ID)
3. ✅ User is linked to the newly created tenant
4. ⚠️ This allows backward compatibility with organizations created outside our system

---

## Data Isolation

All data is strictly isolated per tenant:

- ✅ **Documents**: Filtered by `tenant_id`
- ✅ **Conversations**: Filtered by `tenant_id`
- ✅ **Users**: Belong to specific `tenant_id`
- ✅ **Vector Embeddings**: Stored in tenant-specific Qdrant collections
- ✅ **Validated Answers**: Filtered by `tenant_id`

When a user makes a request:
1. JWT contains `org_id` (WorkOS organization ID)
2. System resolves tenant via `get_current_tenant` dependency
3. All queries filter by `tenant.id`
4. User only sees data for their tenant

---

## API Reference

### Provision Tenant (Admin Only)
```bash
POST /api/v1/tenants/provision
Authorization: Bearer <admin_token>
Content-Type: application/json

{
  "name": "Company Name",
  "domains": ["company.com"]  // Optional
}
```

### User Signup (Public) - Two Flows

#### Flow 1: Founder Creates New Tenant
```bash
POST /api/v1/auth/signup
Content-Type: application/json

{
  "email": "founder@company.com",
  "password": "SecurePass123!",
  "confirm_password": "SecurePass123!",
  "first_name": "John",
  "last_name": "Founder",
  "create_tenant": true,              // Required: Must be true
  "company_name": "Company Name",    // Required: Company name
  "company_domains": ["company.com"]  // Optional: Email domains
  // organization_id: NOT PROVIDED ← Must not be included
}
```

#### Flow 2: Team Member Joins Existing Tenant
```bash
POST /api/v1/auth/signup
Content-Type: application/json

{
  "email": "teammate@company.com",
  "password": "SecurePass123!",
  "confirm_password": "SecurePass123!",
  "first_name": "Jane",
  "last_name": "Team",
  "organization_id": "org_01KB506QM707PJ6J82YZH618TN"  // Required: Get from founder
  // create_tenant: NOT PROVIDED (defaults to false)
  // company_name: NOT PROVIDED
}
```

### Field Requirements Quick Reference

| Field | Founder (create_tenant=true) | Team Member (create_tenant=false) |
|-------|------------------------------|-----------------------------------|
| `create_tenant` | ✅ **Must be `true`** | ❌ Must be `false` or omitted |
| `company_name` | ✅ **Required** | ❌ **Must NOT be provided** |
| `organization_id` | ❌ **Must NOT be provided** | ✅ **Required** |
| `company_domains` | ⚪ Optional | ❌ Must NOT be provided |

---

---

## Admin User Setup

**Important**: Admin users must be created **outside** the normal signup flow. See `docs/ADMIN_USER_SETUP.md` for details on:

- How to bootstrap the first admin user
- Admin user requirements
- How admins are automatically added to provisioned organizations

**Quick Summary**:
- Admin users are created via WorkOS Dashboard or API (not via signup)
- Admin must belong to at least one organization with `admin` role
- When admin provisions a tenant, they're automatically added to that organization
- `organization_id` is **required** in signup (for tenant isolation)

---

## Next Steps

For future enhancements:
- [ ] Self-serve tenant provisioning (users can create their own tenants)
- [ ] Invite links with embedded organization IDs
- [ ] Domain verification workflow
- [ ] Tenant settings management UI
- [ ] Admin bootstrap script for initial setup

