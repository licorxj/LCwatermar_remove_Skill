#!/usr/bin/env python3
"""
Qingmu Hub Client - Submit and track watermark removal tasks

Usage:
    python hub_client.py --submit --video-id VID --coords "x1,y1,x2,y2"
    python hub_client.py --status --request-id RID
    python hub_client.py --download --request-id RID --output result.mp4
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Try to import from watermark_remover project
try:
    import importlib.util
    qmhub_path = Path(__file__).parent.parent.parent / "watermark_remover" / "qmhub"
    if qmhub_path.exists():
        spec = importlib.util.spec_from_file_location("qmhub", qmhub_path / "__init__.py")
        qmhub = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(qmhub)
        QmHubClient = qmhub.QmHubClient
    else:
        raise ImportError("qmhub not found")
except ImportError:
    # Minimal inline client
    import requests

    class QmHubClient:
        """Minimal Qingmu Hub client"""

        def __init__(self, api_key=None, base_url="https://www.licorxj.online"):
            self.api_key = api_key
            self.base_url = base_url.rstrip("/")
            self.session = requests.Session()

        def _headers(self):
            h = {"Content-Type": "application/json"}
            if self.api_key:
                h["Authorization"] = f"Bearer {self.api_key}"
            return h

        def submit_task(self, video_url, coords=None):
            """Submit watermark removal task"""
            data = {
                "video_url": video_url,
                "coords": coords or "0,0,0,0"  # Full frame if no coords
            }
            resp = self.session.post(
                f"{self.base_url}/api/capability/invoke",
                headers=self._headers(),
                json=data,
                timeout=30
            )
            resp.raise_for_status()
            return resp.json()

        def get_status(self, request_id):
            """Get task status"""
            resp = self.session.get(
                f"{self.base_url}/api/capability/tasks/{request_id}",
                headers=self._headers(),
                timeout=30
            )
            resp.raise_for_status()
            return resp.json()

        def download_result(self, request_id, output_path):
            """Download processed video"""
            status = self.get_status(request_id)
            result_url = status.get("result_url")
            if not result_url:
                raise Exception("Result not ready or no result URL")

            resp = self.session.get(result_url, stream=True, timeout=300)
            resp.raise_for_status()

            with open(output_path, 'wb') as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
            return output_path


CONFIG_DIR = Path.home() / ".licorxj"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config():
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text("utf-8"))
        except Exception:
            pass
    return {}


def get_api_key():
    key = os.environ.get("LICORXJ_API_KEY")
    if key:
        return key
    return load_config().get("api_key")


def submit_task(video_url, coords=None, api_key=None):
    """Submit watermark removal task"""
    api_key = api_key or get_api_key()
    if not api_key:
        raise Exception("No API Key. Run: python auth_helper.py --login")

    client = QmHubClient(api_key=api_key)
    print(f"Submitting task...")
    print(f"  Video: {video_url}")
    print(f"  Coords: {coords or 'full frame'}")

    result = client.submit_task(video_url, coords)
    request_id = result.get("request_id") or result.get("id")
    print(f"\nTask submitted! Request ID: {request_id}")
    return result


def check_status(request_id, api_key=None, wait=False):
    """Check task status"""
    api_key = api_key or get_api_key()
    if not api_key:
        raise Exception("No API Key")

    client = QmHubClient(api_key=api_key)

    while True:
        result = client.get_status(request_id)
        status = result.get("status", "unknown")
        print(f"Status: {status}")

        if status in ("completed", "failed", "error"):
            if status == "completed":
                print(f"Result URL: {result.get('result_url')}")
            elif status in ("failed", "error"):
                print(f"Error: {result.get('error', 'Unknown error')}")
            return result

        if not wait:
            return result

        print("Waiting 10 seconds...")
        time.sleep(10)


def download_result(request_id, output_path, api_key=None):
    """Download processed video"""
    api_key = api_key or get_api_key()
    if not api_key:
        raise Exception("No API Key")

    client = QmHubClient(api_key=api_key)
    print(f"Downloading result for {request_id}...")

    result_path = client.download_result(request_id, output_path)
    print(f"Downloaded: {result_path}")
    return result_path


def main():
    parser = argparse.ArgumentParser(description="Qingmu Hub Client")
    parser.add_argument("--submit", action="store_true", help="Submit task")
    parser.add_argument("--video-url", help="Video URL for submission")
    parser.add_argument("--coords", help="Watermark coords: x1,y1,x2,y2")
    parser.add_argument("--status", action="store_true", help="Check status")
    parser.add_argument("--download", action="store_true", help="Download result")
    parser.add_argument("--request-id", help="Request ID")
    parser.add_argument("--output", help="Output file path")
    parser.add_argument("--wait", action="store_true", help="Wait for completion")
    parser.add_argument("--api-key", help="API Key")

    args = parser.parse_args()

    try:
        if args.submit:
            if not args.video_url:
                print("Error: --video-url required for submission", file=sys.stderr)
                sys.exit(1)
            submit_task(args.video_url, args.coords, args.api_key)

        elif args.status:
            if not args.request_id:
                print("Error: --request-id required", file=sys.stderr)
                sys.exit(1)
            check_status(args.request_id, args.api_key, args.wait)

        elif args.download:
            if not args.request_id:
                print("Error: --request-id required", file=sys.stderr)
                sys.exit(1)
            output = args.output or f"result_{args.request_id[:8]}.mp4"
            download_result(args.request_id, output, args.api_key)

        else:
            parser.print_help()

    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
