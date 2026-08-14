"""Read-only smoke check for live role boundaries; never prints bearer tokens."""

import argparse
import os

import httpx


def token(client: httpx.Client, username: str, password: str) -> str:
    response = client.post("/api/auth/login", data={"username": username, "password": password})
    response.raise_for_status()
    return response.json()["access_token"]


def get(client: httpx.Client, path: str, bearer: str) -> int:
    return client.get(path, headers={"Authorization": f"Bearer {bearer}"}).status_code


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    # Credentials are never hard-coded: a real environment's accounts do not
    # necessarily carry the local seed password.
    parser.add_argument("--xodim-username", default="xodim_huquq")
    parser.add_argument("--rahbar-username", default="rahbar_analitika")
    parser.add_argument("--xodim-password", default=os.environ.get("RBAC_CHECK_XODIM_PASSWORD", ""))
    parser.add_argument("--rahbar-password", default=os.environ.get("RBAC_CHECK_RAHBAR_PASSWORD", ""))
    args = parser.parse_args()
    if not args.xodim_password or not args.rahbar_password:
        raise SystemExit(
            "Parollarni --xodim-password/--rahbar-password yoki "
            "RBAC_CHECK_XODIM_PASSWORD/RBAC_CHECK_RAHBAR_PASSWORD orqali bering"
        )
    with httpx.Client(base_url=args.base_url, timeout=15) as client:
        xodim = token(client, args.xodim_username, args.xodim_password)
        rahbar = token(client, args.rahbar_username, args.rahbar_password)
        checks = {
            "xodim_admin_users_denied": get(client, "/api/users", xodim) == 403,
            "xodim_admin_audit_denied": get(client, "/api/audit", xodim) == 403,
            "xodim_system_status_denied": get(client, "/api/system/status", xodim) == 403,
            "xodim_org_profile_denied": get(client, "/api/organization-profile", xodim) == 403,
            "xodim_roles_denied": get(client, "/api/roles", xodim) == 403,
            "xodim_dashboard_denied": get(client, "/api/dashboard", xodim) == 403,
            "xodim_documents_allowed": get(client, "/api/documents", xodim) == 200,
            "xodim_tasks_allowed": get(client, "/api/tasks", xodim) == 200,
            "xodim_ai_readiness_allowed": get(client, "/api/ai/readiness", xodim) == 200,
            "rahbar_dashboard_allowed": get(client, "/api/dashboard", rahbar) == 200,
            "rahbar_tasks_allowed": get(client, "/api/tasks", rahbar) == 200,
            "rahbar_admin_users_denied": get(client, "/api/users", rahbar) == 403,
            "rahbar_admin_audit_denied": get(client, "/api/audit", rahbar) == 403,
            "rahbar_org_profile_denied": get(client, "/api/organization-profile", rahbar) == 403,
            "rahbar_system_status_denied": get(client, "/api/system/status", rahbar) == 403,
        }
        for name, passed in checks.items():
            print(f"{name}: {'PASS' if passed else 'FAIL'}")
        if not all(checks.values()):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
