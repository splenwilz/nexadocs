# Admin User Setup & Bootstrap Flow

This document explains how admin users are created and how they interact with tenant provisioning.

## The Bootstrap Problem

**Question**: How is the first admin user created if there's no existing organization?

**Answer**: Admin users must be created **outside** the normal signup flow, typically through one of these methods:

### Option 1: WorkOS Dashboard (Recommended for Initial Setup)

1. **Create User in WorkOS Dashboard**:
   - Go to WorkOS Dashboard → User Management
   - Create a new user manually
   - Set user metadata: `role: "admin"` OR add user to an organization with `admin` role

2. **Create Organization for Admin** (Optional):
   - Create an organization in WorkOS Dashboard
   - Add the admin user to this organization with `admin` role
   - This organization can be used for admin operations

3. **Sign Up via API** (if user doesn't exist in your DB):
   - Use `POST /api/v1/auth/signup` with the organization ID
   - User will be created in your database and linked to the organization

### Option 2: Direct WorkOS API (Programmatic)

```bash
# Create admin user via WorkOS API
curl -X POST https://api.workos.com/user_management/users \
  -H "Authorization: Bearer $WORKOS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "SecurePass123!",
    "first_name": "Admin",
    "last_name": "User"
  }'

# Create organization for admin
curl -X POST https://api.workos.com/organizations \
  -H "Authorization: Bearer $WORKOS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Admin Organization"
  }'

# Add admin user to organization with admin role
curl -X POST https://api.workos.com/user_management/organization_memberships \
  -H "Authorization: Bearer $WORKOS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_01...",
    "organization_id": "org_01...",
    "role_slug": "admin"
  }'
```

### Option 3: Seed Script (Development)

Create a one-time seed script to bootstrap the first admin:

```python
# scripts/bootstrap_admin.py
import asyncio
from app.core.database import async_session_maker
from app.services.auth import AuthService
from app.services.tenant import TenantService
from app.services.workos_org import WorkOSOrganizationService

async def bootstrap_admin():
    """Create first admin user and organization."""
    workos_orgs = WorkOSOrganizationService()
    tenant_service = TenantService()
    auth_service = AuthService()
    
    # Create admin organization
    org = await workos_orgs.create_organization("Admin Organization")
    
    # Create admin user in WorkOS
    # (Use WorkOS SDK or API directly)
    
    # Add admin to organization
    await workos_orgs.create_organization_membership(
        user_id="admin_user_id",
        organization_id=org["id"],
        role_slug="admin"
    )
    
    # Create tenant for admin organization
    async with async_session_maker() as db:
        tenant = await tenant_service.provision_tenant(
            db,
            name="Admin Organization",
        )
        tenant.workos_organization_id = org["id"]
        await db.commit()

if __name__ == "__main__":
    asyncio.run(bootstrap_admin())
```

---

## Updated Provisioning Flow (With Auto-Admin Addition)

When an admin provisions a new tenant, they are **automatically added** to that organization:

### Flow:

```
1. Admin calls POST /api/v1/tenants/provision
   {
     "name": "Acme Corporation",
     "domains": ["acme.com"]
   }

2. System creates WorkOS organization
   → org_01KB506QM707PJ6J82YZH618TN

3. System creates tenant in database
   → Links tenant to WorkOS org

4. System automatically adds admin to the organization
   → Creates organization membership with "admin" role
   → Admin can now access this tenant

5. Returns tenant with workos_organization_id
```

### Benefits:

- ✅ **Admin automatically has access**: No manual steps needed
- ✅ **Admin can switch contexts**: Can access multiple tenants they've provisioned
- ✅ **Role-based access**: Admin role in the new organization allows full access

---

## Admin User Requirements

### Current System Requirements:

1. **Admin Role in JWT**: 
   - Admin users must have `role: "admin"` in their JWT token
   - This comes from either:
     - Organization membership with `admin` role, OR
     - User metadata with `role: "admin"`

2. **Organization Membership**:
   - Admin users must belong to at least one WorkOS organization
   - This is required for JWT to include organization context

3. **Database Record**:
   - Admin user must exist in your database (`users` table)
   - Linked to a tenant via `tenant_id`

### Admin Access Pattern:

```
Admin User
├─ Belongs to "Admin Organization" (for system-wide admin operations)
├─ Can provision new tenants
├─ Automatically added to each provisioned tenant with admin role
└─ Can access multiple tenants via organization switching
```

---

## Signup Flow Clarification

### Current Behavior:

- **`organization_id` is REQUIRED** in signup (not optional)
- Users must provide a WorkOS organization ID to sign up
- System automatically links user to tenant based on organization ID

### Why Organization ID is Required:

1. **Multi-tenant isolation**: Every user must belong to a tenant
2. **WorkOS requirement**: Users must belong to an organization in WorkOS
3. **Automatic tenant resolution**: System uses organization ID to find/create tenant

### Future Enhancement (Optional):

If you want to support signup without organization ID, you could:

1. **Create default organization** for users without one
2. **Self-serve tenant creation**: Allow users to create their own tenant during signup
3. **Invite-based flow**: Users sign up via invite link with embedded organization ID

---

## Complete Admin Lifecycle

### Initial Setup (One-Time):

```
1. Create admin user in WorkOS (via Dashboard or API)
2. Create admin organization in WorkOS
3. Add admin user to organization with "admin" role
4. Sign up admin user via API (creates DB record)
5. Admin can now provision tenants
```

### Ongoing Operations:

```
1. Admin provisions tenant
   → WorkOS org created
   → Tenant created in DB
   → Admin automatically added to org with admin role ✅

2. Admin can now:
   - Access the tenant they provisioned
   - Manage tenant users
   - Upload documents for tenant
   - View tenant conversations
```

---

## Testing the Flow

### Test Admin Auto-Addition:

```bash
# 1. Login as admin
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/signin \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "..."}' \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

# 2. Provision tenant (admin will be auto-added)
curl -X POST http://localhost:8000/api/v1/tenants/provision \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "name": "Test Tenant",
    "domains": ["test.com"]
  }'

# 3. Verify admin is in organization
# Check WorkOS Dashboard → Organizations → [New Org] → Members
# Admin should appear with "admin" role
```

---

## Summary

### Key Points:

1. ✅ **Admin users are created outside normal signup** (WorkOS Dashboard or API)
2. ✅ **Admin must belong to at least one organization** (for JWT context)
3. ✅ **When admin provisions tenant, they're automatically added** to that organization
4. ✅ **organization_id is required in signup** (for tenant isolation)
5. ✅ **First admin is bootstrapped manually** (one-time setup)

### Recommended Setup:

1. **Initial**: Create first admin via WorkOS Dashboard
2. **Ongoing**: Admins provision tenants and are automatically added
3. **Users**: Sign up with organization ID from provisioned tenant

