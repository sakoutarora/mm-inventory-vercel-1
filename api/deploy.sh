#!/usr/bin/env bash
set -euo pipefail

# ─── Configuration ───────────────────────────────────────────────────────────
FUNCTION_NAME="${LAMBDA_FUNCTION_NAME:-inventory-apis}"
LAYER_NAME="${LAMBDA_LAYER_NAME:-inventory-apis-deps}"
REGION="${AWS_REGION:-ap-south-1}"
RUNTIME="python3.11"
REQUIREMENTS="requirements.txt"
HASH_FILE=".layer-hash"
BUILD_DIR="build"

# ─── Helpers ─────────────────────────────────────────────────────────────────
info()  { echo "▸ $*"; }
ok()    { echo "✓ $*"; }
fail()  { echo "✗ $*" >&2; exit 1; }

compute_hash() {
    if command -v md5sum &>/dev/null; then
        md5sum "$1" | awk '{print $1}'
    else
        md5 -q "$1"
    fi
}

usage() {
    cat <<EOF
Usage: $0 [OPTIONS]

Deploy Lambda function code and/or dependency layer.

Options:
  --full          Build layer (if changed) + deploy code (default)
  --code-only     Deploy function code only, skip layer
  --layer-only    Force rebuild and publish layer only
  --force-layer   Force layer rebuild even if requirements unchanged
  -h, --help      Show this help

Environment variables:
  LAMBDA_FUNCTION_NAME   Lambda function name (default: inventory-apis)
  LAMBDA_LAYER_NAME      Layer name (default: inventory-apis-deps)
  AWS_REGION             AWS region (default: ap-south-1)
EOF
    exit 0
}

# ─── Parse arguments ─────────────────────────────────────────────────────────
MODE="full"
FORCE_LAYER=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --full)        MODE="full"; shift ;;
        --code-only)   MODE="code"; shift ;;
        --layer-only)  MODE="layer"; shift ;;
        --force-layer) FORCE_LAYER=true; shift ;;
        -h|--help)     usage ;;
        *) fail "Unknown option: $1" ;;
    esac
done

# ─── Pre-flight checks ──────────────────────────────────────────────────────
command -v aws  &>/dev/null || fail "AWS CLI not found. Install with: brew install awscli"
command -v pip3 &>/dev/null || fail "pip3 not found."
command -v zip  &>/dev/null || fail "zip not found."

[[ -f "$REQUIREMENTS" ]] || fail "$REQUIREMENTS not found. Run from the api/ directory."

info "Function: $FUNCTION_NAME | Layer: $LAYER_NAME | Region: $REGION"

# ─── Layer Build ─────────────────────────────────────────────────────────────
build_layer() {
    info "Building dependency layer from $REQUIREMENTS ..."
    rm -rf "$BUILD_DIR/layer"
    mkdir -p "$BUILD_DIR/layer/python"

    pip3 install \
        -r "$REQUIREMENTS" \
        -t "$BUILD_DIR/layer/python" \
        --platform manylinux2014_x86_64 \
        --only-binary=:all: \
        --implementation cp \
        --python-version 3.11 \
        --upgrade \
        --quiet

    info "Zipping layer ..."
    (cd "$BUILD_DIR/layer" && zip -r -q ../layer.zip python/)
    ok "Layer zip created ($(du -h "$BUILD_DIR/layer.zip" | awk '{print $1}'))"
}

publish_layer() {
    info "Publishing layer to AWS ..."
    LAYER_ARN=$(aws lambda publish-layer-version \
        --layer-name "$LAYER_NAME" \
        --zip-file "fileb://$BUILD_DIR/layer.zip" \
        --compatible-runtimes "$RUNTIME" \
        --region "$REGION" \
        --query 'LayerVersionArn' \
        --output text)
    ok "Layer published: $LAYER_ARN"

    # Save hash so we can skip next time
    compute_hash "$REQUIREMENTS" > "$HASH_FILE"
}

layer_needs_rebuild() {
    if $FORCE_LAYER; then return 0; fi
    if [[ ! -f "$HASH_FILE" ]]; then return 0; fi
    local current saved
    current=$(compute_hash "$REQUIREMENTS")
    saved=$(cat "$HASH_FILE")
    [[ "$current" != "$saved" ]]
}

# ─── Code Build ──────────────────────────────────────────────────────────────
build_code() {
    info "Packaging function code ..."
    rm -rf "$BUILD_DIR/code"
    mkdir -p "$BUILD_DIR/code"

    # Copy source
    cp -r src "$BUILD_DIR/code/src"

    # Remove __pycache__ to keep zip clean
    find "$BUILD_DIR/code" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

    info "Zipping code ..."
    (cd "$BUILD_DIR/code" && zip -r -q ../code.zip .)
    ok "Code zip created ($(du -h "$BUILD_DIR/code.zip" | awk '{print $1}'))"
}

deploy_code() {
    info "Deploying function code ..."
    aws lambda update-function-code \
        --function-name "$FUNCTION_NAME" \
        --zip-file "fileb://$BUILD_DIR/code.zip" \
        --region "$REGION" \
        --output text \
        --query 'FunctionArn' > /dev/null

    info "Waiting for function update to complete ..."
    aws lambda wait function-updated \
        --function-name "$FUNCTION_NAME" \
        --region "$REGION"
    ok "Function code deployed"
}

attach_layer() {
    local layer_arn="$1"
    info "Attaching layer to function ..."
    aws lambda update-function-configuration \
        --function-name "$FUNCTION_NAME" \
        --layers "$layer_arn" \
        --region "$REGION" \
        --output text \
        --query 'FunctionArn' > /dev/null

    aws lambda wait function-updated \
        --function-name "$FUNCTION_NAME" \
        --region "$REGION"
    ok "Layer attached to function"
}

get_latest_layer_arn() {
    aws lambda list-layer-versions \
        --layer-name "$LAYER_NAME" \
        --region "$REGION" \
        --max-items 1 \
        --query 'LayerVersions[0].LayerVersionArn' \
        --output text
}

# ─── Execute ─────────────────────────────────────────────────────────────────
mkdir -p "$BUILD_DIR"

case "$MODE" in
    layer)
        build_layer
        publish_layer
        attach_layer "$LAYER_ARN"
        ;;

    code)
        build_code
        deploy_code
        ;;

    full)
        LAYER_ARN=""
        if layer_needs_rebuild; then
            build_layer
            publish_layer
        else
            info "Layer unchanged (requirements hash matches), skipping rebuild"
            LAYER_ARN=$(get_latest_layer_arn)
        fi

        build_code
        deploy_code

        if [[ -n "$LAYER_ARN" ]]; then
            attach_layer "$LAYER_ARN"
        fi
        ;;
esac

echo ""
ok "Deploy complete!"
