#!/usr/bin/env bash
set -euo pipefail

# init-site.sh — Scaffold a new site from a Main Branch template
#
# Usage: bash init-site.sh <template> <site-name> [target-directory]
#   template: "saas" or "high-ticket"
#   site-name: name for the repo and directory
#   target-directory: optional, defaults to ~/sites/<site-name>

TEMPLATE="${1:-}"
SITE_NAME="${2:-}"
TARGET_DIR="${3:-}"

# --- Validate arguments ---

if [[ -z "$TEMPLATE" || -z "$SITE_NAME" ]]; then
  echo "Usage: bash init-site.sh <template> <site-name> [target-directory]"
  echo ""
  echo "Templates:"
  echo "  saas         — SaaS / Product landing page"
  echo "  high-ticket  — High-ticket services landing page"
  echo ""
  echo "Example:"
  echo "  bash init-site.sh high-ticket my-coaching-site"
  exit 1
fi

if [[ "$TEMPLATE" != "saas" && "$TEMPLATE" != "high-ticket" ]]; then
  echo "Error: Template must be 'saas' or 'high-ticket'"
  echo "  Got: $TEMPLATE"
  exit 1
fi

# Default target directory
if [[ -z "$TARGET_DIR" ]]; then
  TARGET_DIR="$HOME/sites/$SITE_NAME"
fi

# Template repo URLs
TEMPLATE_REPO="https://github.com/dmthepm/mainbranch-site-template-${TEMPLATE}.git"

# --- Check prerequisites ---

echo "Checking prerequisites..."

if ! command -v node &> /dev/null; then
  echo "Error: Node.js not found. Install Node.js 18+ first."
  exit 1
fi

NODE_VERSION=$(node --version | sed 's/v//' | cut -d. -f1)
if [[ "$NODE_VERSION" -lt 18 ]]; then
  echo "Error: Node.js 18+ required. Found: $(node --version)"
  exit 1
fi

if ! command -v pnpm &> /dev/null; then
  echo "Error: pnpm not found. Install with: npm install -g pnpm"
  exit 1
fi

if ! command -v gh &> /dev/null; then
  echo "Error: GitHub CLI not found. Install with: brew install gh"
  exit 1
fi

if ! gh auth status &> /dev/null; then
  echo "Error: GitHub CLI not authenticated. Run: gh auth login"
  exit 1
fi

echo "  Node.js $(node --version) ✓"
echo "  pnpm $(pnpm --version) ✓"
echo "  gh CLI authenticated ✓"

# --- Create directory ---

if [[ -d "$TARGET_DIR" ]]; then
  echo "Error: Directory already exists: $TARGET_DIR"
  exit 1
fi

echo ""
echo "Creating site: $SITE_NAME"
echo "  Template: $TEMPLATE"
echo "  Location: $TARGET_DIR"
echo ""

mkdir -p "$TARGET_DIR"
cd "$TARGET_DIR"

# --- Initialize repo ---

git init
git checkout -b main

# --- Add template as upstream ---

echo "Fetching template..."
git remote add upstream "$TEMPLATE_REPO"
git fetch upstream

if ! git merge upstream/main --allow-unrelated-histories -m "Initial merge from $TEMPLATE template"; then
  echo "Error: Template merge failed. Check if the template repo exists:"
  echo "  $TEMPLATE_REPO"
  exit 1
fi

echo "Template merged ✓"

# --- Install dependencies ---

echo ""
echo "Installing dependencies..."
pnpm install

# --- Verify build ---

echo ""
echo "Verifying build..."
if pnpm build; then
  echo "Build successful ✓"
else
  echo ""
  echo "Build failed. Common fixes:"
  echo "  - Check Node.js version (need 18+)"
  echo "  - Try: rm -rf node_modules && pnpm install"
  echo "  - Check for TypeScript errors in the template"
  exit 1
fi

# --- Done ---

echo ""
echo "================================================"
echo "  Site scaffolded successfully!"
echo "================================================"
echo ""
echo "  Location: $TARGET_DIR"
echo "  Template: $TEMPLATE"
echo ""
echo "Next steps:"
echo "  1. Create GitHub repo:"
echo "     gh repo create $SITE_NAME --private --source=$TARGET_DIR --push"
echo ""
echo "  2. Deploy via Cloudflare Pages (default, git auto-deploy):"
echo "     python3 .claude/skills/mb-site/scripts/pages.py create-project $SITE_NAME --repo-owner <owner> --repo-name <repo> --branch main"
echo "     (Legacy Netlify path: see references/deployment.md.)"
echo ""
echo "  3. Configure brand:"
echo "     Run /mb-site configure to apply your brand from core business files"
echo ""
