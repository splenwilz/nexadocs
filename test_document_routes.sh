#!/bin/bash
# Test script for document upload API endpoints
# Tests tenant-scoped document operations

set -e

API_URL="http://localhost:8000/api/v1"
EMAIL="knowaloud@gmail.com"
PASSWORD="67945731797Ph!"

echo "=== DOCUMENT API TEST ==="
echo ""

# 1. Login and get access token
echo "✅ 1. LOGIN"
TOKEN=$(curl -s -X POST "$API_URL/auth/signin" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$EMAIL\", \"password\": \"$PASSWORD\"}" \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

if [ -z "$TOKEN" ]; then
  echo "❌ Failed to get access token"
  exit 1
fi

echo "Token obtained: ${TOKEN:0:20}..."
echo ""

# 2. Create a test PDF file (simple text file for testing)
echo "✅ 2. CREATE TEST PDF"
TEST_FILE="/tmp/test_document.pdf"
echo "%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT /F1 12 Tf 100 700 Td (Test Document) Tj ET
endstream
endobj
xref
0 5
trailer
<< /Size 5 /Root 1 0 R >>
startxref
200
%%EOF" > "$TEST_FILE"

if [ ! -f "$TEST_FILE" ]; then
  echo "❌ Failed to create test file"
  exit 1
fi

echo "Test file created: $TEST_FILE ($(wc -c < "$TEST_FILE") bytes)"
echo ""

# 3. Upload document
echo "✅ 3. UPLOAD DOCUMENT"
UPLOAD_RESPONSE=$(curl -s -X POST "$API_URL/documents" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@$TEST_FILE")

DOCUMENT_ID=$(echo "$UPLOAD_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")

if [ -z "$DOCUMENT_ID" ]; then
  echo "❌ Failed to upload document"
  echo "Response: $UPLOAD_RESPONSE"
  exit 1
fi

echo "Document uploaded: $DOCUMENT_ID"
echo "Response: $UPLOAD_RESPONSE" | python3 -m json.tool
echo ""

# 4. List documents
echo "✅ 4. LIST DOCUMENTS"
LIST_RESPONSE=$(curl -s -X GET "$API_URL/documents" \
  -H "Authorization: Bearer $TOKEN")

DOCUMENT_COUNT=$(echo "$LIST_RESPONSE" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))")

echo "Found $DOCUMENT_COUNT document(s)"
echo "Response: $LIST_RESPONSE" | python3 -m json.tool
echo ""

# 5. Get document by ID
echo "✅ 5. GET DOCUMENT"
GET_RESPONSE=$(curl -s -X GET "$API_URL/documents/$DOCUMENT_ID" \
  -H "Authorization: Bearer $TOKEN")

DOCUMENT_FILENAME=$(echo "$GET_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['filename'])")

echo "Document filename: $DOCUMENT_FILENAME"
echo "Response: $GET_RESPONSE" | python3 -m json.tool
echo ""

# 6. Delete document
echo "✅ 6. DELETE DOCUMENT"
DELETE_RESPONSE=$(curl -s -w "\nHTTP Status: %{http_code}\n" -X DELETE "$API_URL/documents/$DOCUMENT_ID" \
  -H "Authorization: Bearer $TOKEN")

echo "Delete response: $DELETE_RESPONSE"
echo ""

# Cleanup test file
rm -f "$TEST_FILE"

echo "=== ALL TESTS COMPLETED ==="

