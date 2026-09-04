#!/usr/bin/env python3
"""
LCWR - QingMu Video Watermark Remover

Complete watermark removal workflow:
1. Authentication (login, get API Key)
2. Get Tencent Cloud credentials
3. Upload video to Tencent Cloud VOD
4. Submit watermark removal task
5. Wait for processing
6. Download result

Usage:
    python watermark_remover.py                              # Interactive mode
    python watermark_remover.py --video video.mp4            # With video
    python watermark_remover.py --video video.mp4 --api-key KEY
"""
import argparse
import json
import os
import sys
import time
import webbrowser
from pathlib import Path

# Add current dir for imports
sys.path.insert(0, str(Path(__file__).parent))

# Import local modules
from auth_helper import (
    get_api_key, prompt_login, fetch_tencent_keys,
    load_config, save_config, CONFIG_FILE, CONFIG_DIR, LOGIN_URL
)

# Constants
OUTPUT_SUFFIX = "_nosub"


def ensure_auth():
    """Ensure user is authenticated, return API Key"""
    api_key = get_api_key()

    if not api_key:
        print("\n" + "=" * 60)
        print("Welcome to LCWR - QingMu Video Watermark Remover")
        print("=" * 60)
        print(f"\nFirst, let's get you authenticated.")
        print(f"Opening: {LOGIN_URL}")

        try:
            webbrowser.open(LOGIN_URL)
        except Exception:
            print(f"Please visit: {LOGIN_URL}")

        api_key = prompt_login()

        # Save and fetch Tencent keys
        try:
            tencent = fetch_tencent_keys(api_key)
            cfg = load_config()
            cfg["api_key"] = api_key
            cfg["tencent_vod_keys"] = tencent
            save_config(cfg)
            print("\nAuthentication successful!")
        except Exception as e:
            print(f"\nWarning: Could not fetch Tencent keys: {e}")
            print("You may need to configure Tencent Cloud keys manually.")

    return api_key


def upload_video_to_vod(video_path, tencent_keys):
    """Upload video to Tencent Cloud VOD"""
    print(f"\n{'='*60}")
    print("Step 1: Uploading video to Tencent Cloud VOD")
    print(f"{'='*60}")
    print(f"Video: {video_path.name}")
    print(f"Size: {video_path.stat().st_size / 1024 / 1024:.1f} MB")

    # Try to import uploader
    try:
        from video_uploader import upload_video
        result = upload_video(
            str(video_path),
            secret_id=tencent_keys["secret_id"],
            secret_key=tencent_keys["secret_key"],
            sub_app_id=tencent_keys["sub_app_id"]
        )
        return result
    except ImportError as e:
        print(f"\nUpload SDK not available: {e}")
        print("\nPlease install one of:")
        print("  pip install vod-python-sdk")
        print("  pip install tencentcloud-sdk-python-vod")
        print("\nOr upload manually and provide video_id/video_url")
        raise
    except Exception as e:
        print(f"\nUpload failed: {e}")
        raise


def submit_watermark_task(api_key, video_url, coords=None):
    """Submit watermark removal task to Qingmu Hub"""
    print(f"\n{'='*60}")
    print("Step 2: Submitting watermark removal task")
    print(f"{'='*60}")

    from hub_client import submit_task
    result = submit_task(video_url, coords, api_key)
    return result


def wait_for_completion(api_key, request_id, timeout=3600):
    """Wait for task completion"""
    print(f"\n{'='*60}")
    print("Step 3: Waiting for processing")
    print(f"{'='*60}")
    print(f"Request ID: {request_id}")
    print("Checking status every 15 seconds...")

    from hub_client import QmHubClient
    client = QmHubClient(api_key=api_key)

    start = time.time()
    while time.time() - start < timeout:
        result = client.get_status(request_id)
        status = result.get("status", "unknown")

        elapsed = int(time.time() - start)
        print(f"  [{elapsed}s] Status: {status}")

        if status == "completed":
            print(f"\nProcessing complete!")
            print(f"Result URL: {result.get('result_url')}")
            return result
        elif status in ("failed", "error"):
            error = result.get("error", "Unknown error")
            raise Exception(f"Processing failed: {error}")

        time.sleep(15)

    raise Exception("Timeout waiting for processing")


def download_result(api_key, request_id, output_path):
    """Download processed video"""
    print(f"\n{'='*60}")
    print("Step 4: Downloading result")
    print(f"{'='*60}")

    from hub_client import download_result as dl
    result_path = dl(request_id, output_path, api_key)
    return result_path


def run_workflow(video_path, api_key=None, coords=None, output_dir=None):
    """
    Run complete watermark removal workflow

    Args:
        video_path: Path to input video
        api_key: API Key (auto-detected if None)
        coords: Watermark coordinates "x1,y1,x2,y2" (None for full frame)
        output_dir: Output directory (None for same as input)
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    # Step 0: Auth
    if not api_key:
        api_key = ensure_auth()

    # Load Tencent keys
    cfg = load_config()
    tencent = cfg.get("tencent_vod_keys")
    if not tencent:
        print("\nFetching Tencent Cloud credentials...")
        tencent = fetch_tencent_keys(api_key)
        cfg["tencent_vod_keys"] = tencent
        save_config(cfg)

    # Step 1: Upload
    upload_result = upload_video_to_vod(video_path, tencent)
    video_id = upload_result.get("file_id")
    video_url = upload_result.get("media_url")

    if not video_url:
        raise Exception("Upload succeeded but no media_url returned")

    print(f"Video ID: {video_id}")
    print(f"Video URL: {video_url}")

    # Step 2: Submit task
    task_result = submit_watermark_task(api_key, video_url, coords)
    request_id = task_result.get("request_id") or task_result.get("id")

    # Step 3: Wait
    final_result = wait_for_completion(api_key, request_id)

    # Step 4: Download
    if output_dir:
        output_dir = Path(output_dir)
    else:
        output_dir = video_path.parent

    output_name = f"{video_path.stem}{OUTPUT_SUFFIX}{video_path.suffix}"
    output_path = output_dir / output_name

    result_path = download_result(api_key, request_id, output_path)

    print(f"\n{'='*60}")
    print("DONE!")
    print(f"{'='*60}")
    print(f"Input:  {video_path}")
    print(f"Output: {result_path}")
    print(f"\nWatermark removed successfully!")

    return result_path


def main():
    parser = argparse.ArgumentParser(
        description="LCWR - QingMu Video Watermark Remover",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode
  python watermark_remover.py

  # With video file
  python watermark_remover.py --video path/to/video.mp4

  # With API Key
  python watermark_remover.py --video video.mp4 --api-key YOUR_KEY

  # With watermark coordinates
  python watermark_remover.py --video video.mp4 --coords "100,100,200,200"

  # Specify output directory
  python watermark_remover.py --video video.mp4 --output-dir ./output
"""
    )

    parser.add_argument("--video", help="Input video file path")
    parser.add_argument("--api-key", help="API Key (or set LICORXJ_API_KEY env)")
    parser.add_argument("--coords", help='Watermark coordinates: "x1,y1,x2,y2"')
    parser.add_argument("--output-dir", help="Output directory")
    parser.add_argument("--login", action="store_true", help="Login only")

    args = parser.parse_args()

    if args.login:
        from auth_helper import do_login
        do_login()
        return

    if not args.video:
        # Interactive mode
        print("\n" + "=" * 60)
        print("LCWR - QingMu Video Watermark Remover")
        print("=" * 60)
        print("\nNo video specified. Please provide a video file.")
        print("Usage: python watermark_remover.py --video path/to/video.mp4")
        print("\nOr run with --login to set up authentication first.")
        return

    try:
        result = run_workflow(
            video_path=args.video,
            api_key=args.api_key,
            coords=args.coords,
            output_dir=args.output_dir
        )
        print(f"\nResult saved to: {result}")

    except KeyboardInterrupt:
        print("\n\nCancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
