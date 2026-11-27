#!/usr/bin/env bash

REPO="git-mb001/honey-barrel"

echo "== GitHub Repo Health Check =="
echo "Repo: $REPO"
echo ""

# 1. GitHub CLI access check
echo "[1] gh repo view"
gh repo view "$REPO" >/dev/null 2>&1
if [ $? -eq 0 ]; then
  echo "OK: gh can access repo"
else
  echo "FAIL: gh cannot access repo"
fi

# 2. REST API repo GET (critical test)
echo ""
echo "[2] REST API repo GET"
curl -s -o /dev/null -w "%{http_code}" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/$REPO | grep -q "200"

if [ $? -eq 0 ]; then
  echo "OK: REST API can GET repo"
else
  echo "FAIL: REST API GET repo (likely permission issue)"
fi

# 3. SEARCH API check
echo ""
echo "[3] Search API"
curl -s "https://api.github.com/search/repositories?q=honey-barrel+user:git-mb001" | grep -q "honey-barrel"

if [ $? -eq 0 ]; then
  echo "OK: repo visible in search index"
else
  echo "FAIL: repo NOT in search index"
fi

# 4. Compare SEARCH vs GET consistency
echo ""
echo "[4] Consistency check"
SEARCH_OK=$(curl -s "https://api.github.com/search/repositories?q=honey-barrel+user:git-mb001" | grep -c "honey-barrel")
GET_OK=$(curl -s -o /dev/null -w "%{http_code}" https://api.github.com/repos/$REPO)

echo "Search hits: $SEARCH_OK"
echo "GET status: $GET_OK"

if [ "$SEARCH_OK" -gt 0 ] && [ "$GET_OK" != "200" ]; then
  echo "WARNING: SEARCH works but GET fails → GitHub App / permissions issue"
fi
