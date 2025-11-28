# Self-Serve Tenant Signup Flow

This document describes how new companies can sign up and create their own tenant without requiring manual admin intervention.

## Overview

**Problem Solved**: Previously, new companies had to go through the same manual bootstrap process as the first admin (creating WorkOS organization manually, etc.). Now, companies can self-serve and create their own tenant during signup.

## Two Signup Flows

### Flow 1: Join Existing Tenant (Team Members)

**Use Case**: Team member joining a company that already has a tenant.

**Field Requirements**:
- ✅ `create_tenant`: `false` (or omit - defaults to false)
- ✅ `organization_id`: **REQUIRED** - Must provide the WorkOS organization ID
- ❌ `company_name`: **NOT PROVIDED** - Not needed
- ❌ `company_domains`: **NOT PROVIDED** - Not needed

**Request**:
```json
{
  "email": "teammate@company.com",
  "password": "SecurePass123!",
  "confirm_password": "SecurePass123!",
  "first_name": "John",
  "last_name": "Doe",
  "organization_id": "org_01KB506QM707PJ6J82YZH618TN"  ← Required: Get from founder/admin
}
```

**What Happens**:
1. Creates WorkOS user
2. Adds user to existing organization
3. Resolves tenant by organization ID
4. Links user to tenant
5. User gets "member" role (not admin)

**Validation Rules**:
- If `create_tenant` is `false` (or omitted) → `organization_id` **MUST** be provided
- Error if `organization_id` is missing: "Either organization_id must be provided OR create_tenant must be true with company_name"

---

### Flow 2: Self-Serve Tenant Creation (Company Founders)

**Use Case**: Company founder creating a new tenant for their company.

**Field Requirements**:
- ✅ `create_tenant`: `true` - **REQUIRED**
- ✅ `company_name`: **REQUIRED** - Company/tenant name
- ❌ `organization_id`: **MUST NOT BE PROVIDED** - Will error if provided
- ⚪ `company_domains`: Optional - List of email domains

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

**Validation Rules**:
- If `create_tenant` is `true` → `company_name` **MUST** be provided
- If `create_tenant` is `true` → `organization_id` **MUST NOT** be provided
- Error if both provided: "Cannot provide both organization_id and create_tenant=true. Choose one."
- Error if `company_name` missing: "company_name is required when create_tenant is true"

**What Happens**:
1. ✅ **Creates WorkOS Organization**:
   - Creates new WorkOS organization with company name
   - Associates optional domains (in `pending` state)
   - Returns WorkOS organization ID

2. ✅ **Creates Tenant in Database**:
   - Creates tenant record with auto-generated slug
   - Links tenant to WorkOS organization
   - Sets `is_active = true`

3. ✅ **Creates WorkOS User**:
   - Creates user in WorkOS User Management
   - User must verify email before login

4. ✅ **Adds User to Organization with Admin Role**:
   - Creates organization membership
   - Assigns `admin` role to the first user
   - First user becomes admin of their own tenant

5. ✅ **Creates Local User Record**:
   - Creates user in PostgreSQL database
   - Links user to the newly created tenant

**Response**:
```json
{
  "user": {
    "id": "user_01KB51CBQMWPGPBYJ4014145JV",
    "email": "founder@newcompany.com",
    "first_name": "John",
    "last_name": "Founder",
    "email_verified": false,
    ...
  },
  "message": "User created successfully. Please verify your email to login."
}
```

---

## Complete Self-Serve Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. COMPANY FOUNDER SIGNS UP                                     │
└─────────────────────────────────────────────────────────────────┘
   POST /api/v1/auth/signup
   {
     "email": "founder@newcompany.com",
     "password": "SecurePass123!",
     "create_tenant": true,
     "company_name": "New Company Inc",
     "company_domains": ["newcompany.com"]
   }

┌─────────────────────────────────────────────────────────────────┐
│ 2. SYSTEM CREATES EVERYTHING AUTOMATICALLY                      │
└─────────────────────────────────────────────────────────────────┘
   System:
   ├─ Creates WorkOS Organization → org_01KB51CBQMWPGPBYJ4014145JV
   ├─ Creates Tenant in DB
   │  ├─ name: "New Company Inc"
   │  ├─ slug: "new-company-inc" (auto-generated)
   │  └─ workos_organization_id: org_01KB51CBQMWPGPBYJ4014145JV
   ├─ Creates WorkOS User
   ├─ Adds User to Organization with "admin" role ✅
   └─ Creates Local User Record linked to tenant

┌─────────────────────────────────────────────────────────────────┐
│ 3. FOUNDER VERIFIES EMAIL                                        │
└─────────────────────────────────────────────────────────────────┘
   Founder receives verification email
   → Clicks verification link
   → Email verified

┌─────────────────────────────────────────────────────────────────┐
│ 4. FOUNDER LOGS IN AS ADMIN                                      │
└─────────────────────────────────────────────────────────────────┘
   POST /api/v1/auth/signin
   {
     "email": "founder@newcompany.com",
     "password": "SecurePass123!"
   }
   
   → JWT contains: role: "admin", org_id: org_01KB51CBQMWPGPBYJ4014145JV
   → Founder can now:
      - Upload documents for their company
      - Invite team members (they'll use the organization_id)
      - Manage their tenant

┌─────────────────────────────────────────────────────────────────┐
│ 5. FOUNDER INVITES TEAM MEMBERS                                  │
└─────────────────────────────────────────────────────────────────┘
   Team members sign up with:
   {
     "email": "teammate@newcompany.com",
     "password": "SecurePass123!",
     "organization_id": "org_01KB51CBQMWPGPBYJ4014145JV"  // From founder
   }
   
   → Team members join the same tenant
   → They get "member" role (not admin)
```

---

## Comparison: Old vs New Flow

### ❌ Old Flow (Manual Bootstrap Required)

1. Admin manually creates WorkOS organization in Dashboard
2. Admin copies organization ID
3. Admin provisions tenant via API
4. Admin shares organization ID with company founder
5. Founder signs up with organization ID
6. Founder is just a member (not admin)

**Problems**:
- ❌ Manual steps required
- ❌ Founder not automatically admin
- ❌ Not scalable for many companies

### ✅ New Flow (Self-Serve)

1. Founder signs up with `create_tenant=true`
2. System creates everything automatically
3. Founder becomes admin automatically
4. Founder can invite team members

**Benefits**:
- ✅ Fully automated
- ✅ No manual admin steps
- ✅ Founder is admin of their tenant
- ✅ Scalable for many companies
- ✅ Better user experience

---

## API Reference

### Signup Endpoint

**Endpoint**: `POST /api/v1/auth/signup` (Public)

**Supports Two Flows**: See field requirements below

---

### Flow 1: Join Existing Tenant (Team Members)

**Request Body**:
```json
{
  "email": "teammate@company.com",
  "password": "SecurePass123!",
  "confirm_password": "SecurePass123!",
  "first_name": "John",
  "last_name": "Doe",
  "organization_id": "org_01KB506QM707PJ6J82YZH618TN"  // Required
}
```

**Required Fields**:
- `email`: User email address
- `password`: User password (min 8 chars, must contain uppercase, lowercase, number)
- `confirm_password`: Password confirmation (must match password)
- `organization_id`: WorkOS organization ID (get from founder/admin)

**Optional Fields**:
- `first_name`: User first name
- `last_name`: User last name

**Validation**:
- ❌ `create_tenant`: Must be `false` or omitted
- ❌ `company_name`: Must NOT be provided
- ✅ `organization_id`: **MUST** be provided

---

### Flow 2: Create New Tenant (Company Founders)

**Request Body**:
```json
{
  "email": "founder@company.com",
  "password": "SecurePass123!",
  "confirm_password": "SecurePass123!",
  "first_name": "John",
  "last_name": "Founder",
  "create_tenant": true,              // Required: Must be true
  "company_name": "Company Name",    // Required: Company/tenant name
  "company_domains": ["company.com"]  // Optional: Email domains
}
```

**Required Fields**:
- `email`: User email address
- `password`: User password (min 8 chars, must contain uppercase, lowercase, number)
- `confirm_password`: Password confirmation (must match password)
- `create_tenant`: **MUST** be `true`
- `company_name`: Company/tenant name (required when `create_tenant` is true)

**Optional Fields**:
- `first_name`: User first name
- `last_name`: User last name
- `company_domains`: List of email domains to associate with organization

**Validation**:
- ✅ `create_tenant`: **MUST** be `true`
- ✅ `company_name`: **MUST** be provided
- ❌ `organization_id`: **MUST NOT** be provided (will error if provided)

**Response** (201 Created):
```json
{
  "user": {
    "id": "user_01...",
    "email": "founder@company.com",
    "first_name": "John",
    "last_name": "Founder",
    "email_verified": false,
    ...
  },
  "message": "User created successfully. Please verify your email to login."
}
```

**Error Responses**:
- `400 Bad Request`: Validation errors (missing fields, password mismatch, etc.)
- `409 Conflict`: Email already exists
- `500 Internal Server Error`: Failed to create organization or tenant

---

## Field Requirements Summary

### Quick Reference Table

| Field | Founder (create_tenant=true) | Team Member (create_tenant=false) |
|-------|------------------------------|-----------------------------------|
| `email` | ✅ Required | ✅ Required |
| `password` | ✅ Required | ✅ Required |
| `confirm_password` | ✅ Required | ✅ Required |
| `create_tenant` | ✅ **Must be `true`** | ❌ Must be `false` or omitted |
| `company_name` | ✅ **Required** | ❌ **Must NOT be provided** |
| `organization_id` | ❌ **Must NOT be provided** | ✅ **Required** |
| `company_domains` | ⚪ Optional | ❌ Must NOT be provided |
| `first_name` | ⚪ Optional | ⚪ Optional |
| `last_name` | ⚪ Optional | ⚪ Optional |

### Validation Rules

#### Password Requirements:
- Minimum 8 characters
- At least one uppercase letter
- At least one lowercase letter
- At least one number

#### Company Name (when create_tenant=true):
- Minimum 1 character
- Maximum 255 characters
- Used to generate unique slug automatically

#### Domains (when create_tenant=true):
- Optional list of email domains
- Domains are created in `pending` state (must be verified later)
- Format: `["company.com", "subdomain.company.com"]`

#### Mutual Exclusivity:
- **Cannot provide both** `organization_id` and `create_tenant=true`
- Error: "Cannot provide both organization_id and create_tenant=true. Choose one."

#### Required Field Validation:
- If `create_tenant=true` → `company_name` **MUST** be provided
- If `create_tenant=false` (or omitted) → `organization_id` **MUST** be provided

---

## Security Considerations

1. **Email Verification Required**:
   - Users must verify email before they can login
   - Prevents fake account creation

2. **Admin Role Assignment**:
   - Only the first user (founder) gets admin role
   - Subsequent users joining via `organization_id` get member role

3. **Tenant Isolation**:
   - All data is strictly isolated per tenant
   - Users can only access their own tenant's data

4. **Domain Verification**:
   - Domains are created in `pending` state
   - Must be verified via DNS TXT records in WorkOS Dashboard

---

## Testing

### Test Self-Serve Signup:

```bash
curl -X POST http://localhost:8000/api/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "founder@newcompany.com",
    "password": "SecurePass123!",
    "confirm_password": "SecurePass123!",
    "first_name": "John",
    "last_name": "Founder",
    "create_tenant": true,
    "company_name": "New Company Inc",
    "company_domains": ["newcompany.com"]
  }'
```

### Verify Tenant Created:

```bash
# Login as system admin
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/signin \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@system.com", "password": "..."}' \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

# List tenants (should see "New Company Inc")
curl -X GET http://localhost:8000/api/v1/tenants \
  -H "Authorization: Bearer $TOKEN"
```

---

## Summary

✅ **Self-serve tenant creation is now fully automated**

- Companies can sign up and create their own tenant
- First user automatically becomes admin
- No manual admin intervention required
- Scalable for production use

**Next Steps for Founders**:
1. Sign up with `create_tenant=true`
2. Verify email
3. Login and start using the system
4. Invite team members with the `organization_id` from their tenant

