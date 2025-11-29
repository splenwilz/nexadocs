# WorkOS JWT Template Configuration

## Overview
This template adds role information to JWT tokens so the admin authorization check can work.

## JWT Template to Add in WorkOS Dashboard

Go to: **WorkOS Dashboard → Authentication → Sessions → Configure JWT Template**

Paste this template:

```json
{
  "role": "{{ organization_membership.role || user.metadata.role }}",
  "organization_id": "{{ organization.id }}",
  "organization_name": "{{ organization.name }}"
}
```

**Important**: 
- Removed the `|| 'member'` fallback - if role is not set, the `role` claim will be **removed** from the JWT (WorkOS automatically removes null values)
- Only users with explicit `admin` role will have `"role": "admin"` in their JWT
- Users without a role will not have the `role` claim at all

## Alternative Template (If Using User Metadata)

If you're storing admin role in user metadata instead of organization membership:

```json
{
  "role": "{{ user.metadata.role }}"
}
```

**Important**: No fallback value - role claim only appears if `user.metadata.role` is set.

## How to Set Admin Role

### Option 1: Using Organization Membership (Recommended)

1. Create an organization in WorkOS Dashboard
2. Add your user to the organization
3. Set the membership role to `admin`
4. The JWT will automatically include `role: "admin"`

### Option 2: Using User Metadata

1. Go to WorkOS Dashboard → User Management
2. Find your user: `knowaloud@gmail.com`
3. Edit user metadata
4. Add: `role: "admin"`
5. The JWT will include `role: "admin"` from metadata

## Template Explanation

- **`role`**: Single string role (e.g., "admin")
  - Checks `organization_membership.role` first (if user is in an org)
  - Falls back to `user.metadata.role`
  - **If neither exists, the `role` claim is removed from JWT** (WorkOS null handling)
  - Your code checks: `role == 'admin'` or `role == 'Admin'`
  - Users without admin role will not have `role` claim, so `session_data.get('role')` returns `None`, and admin check fails (correct behavior)

- **`organization_id`**: Organization ID (useful for multi-tenant scenarios)
- **`organization_name`**: Organization name (useful for display/logging)

## Testing After Configuration

1. Save the JWT template in WorkOS Dashboard
2. Log out and log back in to get a new JWT
3. Decode the JWT to verify it contains:
   ```json
   {
     "role": "admin",
     "organization_id": "...",
     ...
   }
   ```
4. Re-run the test script: `./test_tenant_routes.sh`

## Reference

- [WorkOS JWT Templates Documentation](https://workos.com/docs/authkit/jwt-templates/example-usage)
- [WorkOS Organization Memberships](https://workos.com/docs/authkit/organizations)

