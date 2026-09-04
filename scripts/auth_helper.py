#!/usr/bin/env python3
"""
Authentication helper for LCWR skill

Usage:
    python auth_helper.py --login          # Login and get API Key
    python auth_helper.py --show-keys      # Show saved keys
    python auth_helper.py --clear          # Clear saved auth
"""
import argparse
import json
import os
import sys
import webbrowser
from pathlib import Path

# Add parent dir for imports
sys.path.insert(0, str(Path(__file__).parent))

CONFIG_DIR = Path.home() / ".licorxj"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOGIN_URL = "https://www.licorxj.online/capability-hub"
SOFTWARE_ID = "qm0101"


def load_config():
    """Load config file"""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text("utf-8"))
        except Exception:
            pass
    return {}


def save_config(config):
    """Save config file"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), "utf-8")
    print(f"Config saved: {CONFIG_FILE}")


def get_api_key():
    """Get API Key from env or config"""
    # 1. Environment variable
    key = os.environ.get("LICORXJ_API_KEY")
    if key:
        return key
    # 2. Config file
    cfg = load_config()
    return cfg.get("api_key")


def prompt_login():
    """Guide user to login and get API Key"""
    print("\n" + "=" * 60)
    print("First Use: Login to Qingmu Platform")
    print("=" * 60)
    print(f"\nOpening: {LOGIN_URL}")
    print("\nSteps:")
    print("1. Register or login")
    print("2. Find API Key in user center")
    print("3. Copy and paste below\n")

    try:
        webbrowser.open(LOGIN_URL)
    except Exception:
        print(f"Cannot open browser. Visit: {LOGIN_URL}")

    while True:
        key = input("\nEnter API Key: ").strip()
        if key:
            return key
        print("API Key cannot be empty")


def fetch_tencent_keys(api_key):
    """Fetch Tencent Cloud VOD keys via API"""
    try:
        from cloud_auth_user_client import CloudAuthUserClient
    except ImportError:
        # Try importing from same directory
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "cloud_auth_user_client",
            Path(__file__).parent / "cloud_auth_user_client.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        CloudAuthUserClient = mod.CloudAuthUserClient

    client = CloudAuthUserClient()
    client.set_token(api_key)

    print(f"\nFetching Tencent Cloud keys (software: {SOFTWARE_ID})...")
    result = client.get_software_secure_data(SOFTWARE_ID)

    if not result.get("has_data"):
        raise Exception("Software has no configured data")
    if result.get("error"):
        raise Exception(f"Error: {result['error']}")

    data = result.get("data", {})
    if "tencent" not in data:
        raise Exception(f"Missing tencent field: {data}")

    tencent = data["tencent"]
    for k in ["secret_id", "secret_key", "sub_app_id"]:
        if k not in tencent:
            raise Exception(f"Missing {k} in tencent config")

    return tencent


def do_login():
    """Full login flow"""
    api_key = get_api_key()

    if not api_key:
        api_key = prompt_login()

    # Validate and fetch Tencent keys
    try:
        tencent = fetch_tencent_keys(api_key)
        print("\nTencent Cloud keys retrieved successfully!")
        print(f"  Secret ID: {tencent['secret_id'][:10]}...")
        print(f"  Sub App ID: {tencent['sub_app_id']}")

        # Save everything
        cfg = load_config()
        cfg["api_key"] = api_key
        cfg["tencent_vod_keys"] = tencent
        save_config(cfg)

        print("\nLogin successful! You can now use the watermark remover.")
        return True

    except Exception as e:
        print(f"\nError: {e}")
        print("Please check your API Key and try again.")
        return False


def show_keys():
    """Show saved keys"""
    cfg = load_config()
    api_key = cfg.get("api_key")
    tencent = cfg.get("tencent_vod_keys")

    print("\nSaved Authentication Info:")
    print("-" * 40)

    if api_key:
        print(f"API Key: {api_key[:20]}...")
    else:
        print("API Key: Not saved")

    if tencent:
        print(f"\nTencent Cloud Keys:")
        print(f"  Secret ID: {tencent.get('secret_id', 'N/A')}")
        print(f"  Secret Key: {tencent.get('secret_key', 'N/A')[:10]}...")
        print(f"  Sub App ID: {tencent.get('sub_app_id', 'N/A')}")
    else:
        print("\nTencent Cloud Keys: Not saved")


def clear_auth():
    """Clear saved auth info"""
    cfg = load_config()
    cfg.pop("api_key", None)
    cfg.pop("tencent_vod_keys", None)

    if not cfg:
        CONFIG_FILE.unlink(missing_ok=True)
        print(f"Config deleted: {CONFIG_FILE}")
    else:
        save_config(cfg)
        print("Auth info cleared")


def main():
    parser = argparse.ArgumentParser(description="LCWR Authentication Helper")
    parser.add_argument("--login", action="store_true", help="Login and get API Key")
    parser.add_argument("--show-keys", action="store_true", help="Show saved keys")
    parser.add_argument("--clear", action="store_true", help="Clear saved auth")
    parser.add_argument("--get-api-key", action="store_true", help="Print API Key")

    args = parser.parse_args()

    if args.login:
        do_login()
    elif args.show_keys:
        show_keys()
    elif args.clear:
        confirm = input("Clear all auth info? (y/N): ").strip().lower()
        if confirm in ("y", "yes"):
            clear_auth()
        else:
            print("Cancelled")
    elif args.get_api_key:
        key = get_api_key()
        if key:
            print(key)
        else:
            print("No API Key found", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
