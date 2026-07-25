from src.lib.response import json_response
from src.routes import (
    handle_admin_create_category,
    handle_admin_create_item,
    handle_admin_create_user,
    handle_admin_meta,
    handle_admin_update_item,
    handle_dashboard_summary,
    handle_get_inventory_items,
    handle_login,
    handle_update_inventory,
)


ROUTES = {
    ("POST", "/api/v1/auth/login"): handle_login,
    ("GET", "/api/v1/inventory/items"): handle_get_inventory_items,
    ("POST", "/api/v1/inventory/update"): handle_update_inventory,
    ("GET", "/api/v1/dashboard/summary"): handle_dashboard_summary,
    ("GET", "/api/v1/admin/meta"): handle_admin_meta,
    ("POST", "/api/v1/admin/categories"): handle_admin_create_category,
    ("POST", "/api/v1/admin/items"): handle_admin_create_item,
    ("PATCH", "/api/v1/admin/items"): handle_admin_update_item,
    ("POST", "/api/v1/admin/users"): handle_admin_create_user,

    ("POST", "/prod/api/v1/auth/login"): handle_login,
    ("GET", "/prod/api/v1/inventory/items"): handle_get_inventory_items,
    ("POST", "/prod/api/v1/inventory/update"): handle_update_inventory,
    ("GET", "/prod/api/v1/dashboard/summary"): handle_dashboard_summary,
    ("GET", "/prod/api/v1/admin/meta"): handle_admin_meta,
    ("POST", "/prod/api/v1/admin/categories"): handle_admin_create_category,
    ("POST", "/prod/api/v1/admin/items"): handle_admin_create_item,
    ("PATCH", "/prod/api/v1/admin/items"): handle_admin_update_item,
    ("POST", "/prod/api/v1/admin/users"): handle_admin_create_user,

    ("POST", "/dev/api/v1/auth/login"): handle_login,
    ("GET", "/dev/api/v1/inventory/items"): handle_get_inventory_items,
    ("POST", "/dev/api/v1/inventory/update"): handle_update_inventory,
    ("GET", "/dev/api/v1/dashboard/summary"): handle_dashboard_summary,
    ("GET", "/dev/api/v1/admin/meta"): handle_admin_meta,
    ("POST", "/dev/api/v1/admin/categories"): handle_admin_create_category,
    ("POST", "/dev/api/v1/admin/items"): handle_admin_create_item,
    ("PATCH", "/dev/api/v1/admin/items"): handle_admin_update_item,
    ("POST", "/dev/api/v1/admin/users"): handle_admin_create_user,

    ("POST", "/stage/api/v1/auth/login"): handle_login,
    ("GET", "/stage/api/v1/inventory/items"): handle_get_inventory_items,
    ("POST", "/stage/api/v1/inventory/update"): handle_update_inventory,
    ("GET", "/stage/api/v1/dashboard/summary"): handle_dashboard_summary,
    ("GET", "/stage/api/v1/admin/meta"): handle_admin_meta,
    ("POST", "/stage/api/v1/admin/categories"): handle_admin_create_category,
    ("POST", "/stage/api/v1/admin/items"): handle_admin_create_item,
    ("PATCH", "/stage/api/v1/admin/items"): handle_admin_update_item,
    ("POST", "/stage/api/v1/admin/users"): handle_admin_create_user,
}


def _extract_path(event: dict) -> str:
    # Support API Gateway REST and HTTP API payload formats.
    return event.get("path") or event.get("rawPath") or ""


def _extract_method(event: dict) -> str:
    method = event.get("httpMethod")
    if method:
        return method.upper()

    request_context = event.get("requestContext") or {}
    http_context = request_context.get("http") or {}
    return (http_context.get("method") or "").upper()


def lambda_handler(event, context):
    method = _extract_method(event)
    path = _extract_path(event)

    if method == "OPTIONS":
        return json_response(200, {"ok": True})

    handler = ROUTES.get((method, path))
    if not handler:
        return json_response(404, {"message": f"No route for {method} {path}"})

    return handler(event, context)
