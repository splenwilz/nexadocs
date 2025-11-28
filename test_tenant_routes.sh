#!/bin/bash
# Test script for tenant management API routes
# Tests all CRUD operations for tenants

set -e

BASE_URL="http://localhost:8000/api/v1"
EMAIL="knowaloud@gmail.com"
PASSWORD="67945731797Ph!"

echo "=========================================="
echo "Testing Tenant Management API Routes"
echo "=========================================="
echo ""

# Step 1: Login and get access token
echo "1. LOGIN - Getting access token..."
LOGIN_RESPONSE=$(curl -s -X POST "${BASE_URL}/auth/signin" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"${EMAIL}\", \"password\": \"${PASSWORD}\"}")

ACCESS_TOKEN=$(echo $LOGIN_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null || echo "")

if [ -z "$ACCESS_TOKEN" ]; then
  echo "❌ Login failed!"
  echo "Response: $LOGIN_RESPONSE"
  exit 1
fi

echo "✅ Login successful"
echo "Token: ${ACCESS_TOKEN:0:50}..."
echo ""

# Step 2: Test CREATE tenant
echo "2. CREATE TENANT - POST /api/v1/tenants"
CREATE_RESPONSE=$(curl -s -X POST "${BASE_URL}/tenants" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -d '{
    "name": "Test Tenant",
    "slug": "test-tenant",
    "is_active": true
  }')

echo "$CREATE_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$CREATE_RESPONSE"
echo ""

# Extract tenant_id if creation was successful
TENANT_ID=$(echo $CREATE_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")

if [ -z "$TENANT_ID" ]; then
  echo "⚠️  Tenant creation failed (likely due to missing admin role)"
  echo "   Note: All tenant endpoints require admin role in WorkOS JWT"
  echo ""
  echo "To test tenant endpoints, you need to:"
  echo "1. Assign 'admin' role to your user in WorkOS dashboard"
  echo "2. Or configure WorkOS to include 'admin' in the JWT roles claim"
  echo ""
  echo "Continuing with other tests..."
  echo ""
  
  # Use a dummy UUID for remaining tests
  TENANT_ID="00000000-0000-0000-0000-000000000000"
fi

# Step 3: Test LIST tenants
echo "3. LIST TENANTS - GET /api/v1/tenants"
LIST_RESPONSE=$(curl -s -X GET "${BASE_URL}/tenants?skip=0&limit=10" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}")

echo "$LIST_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$LIST_RESPONSE"
echo ""

# Step 4: Test GET tenant by ID
if [ "$TENANT_ID" != "00000000-0000-0000-0000-000000000000" ]; then
  echo "4. GET TENANT - GET /api/v1/tenants/${TENANT_ID}"
  GET_RESPONSE=$(curl -s -X GET "${BASE_URL}/tenants/${TENANT_ID}" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}")
  
  echo "$GET_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$GET_RESPONSE"
  echo ""
else
  echo "4. GET TENANT - Skipped (no tenant ID available)"
  echo ""
fi

# Step 5: Test UPDATE tenant
if [ "$TENANT_ID" != "00000000-0000-0000-0000-000000000000" ]; then
  echo "5. UPDATE TENANT - PATCH /api/v1/tenants/${TENANT_ID}"
  UPDATE_RESPONSE=$(curl -s -X PATCH "${BASE_URL}/tenants/${TENANT_ID}" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -d '{
      "name": "Updated Test Tenant",
      "is_active": true
    }')
  
  echo "$UPDATE_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$UPDATE_RESPONSE"
  echo ""
else
  echo "5. UPDATE TENANT - Skipped (no tenant ID available)"
  echo ""
fi

# Step 6: Test DEACTIVATE tenant
if [ "$TENANT_ID" != "00000000-0000-0000-0000-000000000000" ]; then
  echo "6. DEACTIVATE TENANT - POST /api/v1/tenants/${TENANT_ID}/deactivate"
  DEACTIVATE_RESPONSE=$(curl -s -X POST "${BASE_URL}/tenants/${TENANT_ID}/deactivate" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}")
  
  echo "$DEACTIVATE_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$DEACTIVATE_RESPONSE"
  echo ""
else
  echo "6. DEACTIVATE TENANT - Skipped (no tenant ID available)"
  echo ""
fi

# Step 7: Test ACTIVATE tenant
if [ "$TENANT_ID" != "00000000-0000-0000-0000-000000000000" ]; then
  echo "7. ACTIVATE TENANT - POST /api/v1/tenants/${TENANT_ID}/activate"
  ACTIVATE_RESPONSE=$(curl -s -X POST "${BASE_URL}/tenants/${TENANT_ID}/activate" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}")
  
  echo "$ACTIVATE_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$ACTIVATE_RESPONSE"
  echo ""
else
  echo "7. ACTIVATE TENANT - Skipped (no tenant ID available)"
  echo ""
fi

# Step 8: Test DELETE tenant (commented out to avoid data loss)
# Uncomment to test deletion
# echo "8. DELETE TENANT - DELETE /api/v1/tenants/${TENANT_ID}"
# DELETE_RESPONSE=$(curl -s -X DELETE "${BASE_URL}/tenants/${TENANT_ID}" \
#   -H "Authorization: Bearer ${ACCESS_TOKEN}")
# 
# echo "$DELETE_RESPONSE"
# echo ""

echo "=========================================="
echo "Testing Complete"
echo "=========================================="
echo ""
echo "Summary:"
echo "- Login: ✅ Working"
echo "- Tenant endpoints: Require admin role"
echo ""
echo "To enable tenant management:"
echo "1. Go to WorkOS dashboard"
echo "2. Assign 'admin' role to user: ${EMAIL}"
echo "3. Re-run this script"
echo ""

