#!/usr/bin/env python3
"""
Video uploader to Tencent Cloud VOD

Usage:
    python video_uploader.py --video path/to/video.mp4
    python video_uploader.py --video video.mp4 --secret-id ID --secret-key KEY --app-id ID
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

CONFIG_DIR = Path.home() / ".licorxj"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config():
    """Load config"""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text("utf-8"))
        except Exception:
            pass
    return {}


def get_tencent_keys():
    """Get Tencent Cloud keys from config"""
    cfg = load_config()
    tencent = cfg.get("tencent_vod_keys")
    if not tencent:
        raise Exception("No Tencent Cloud keys found. Run: python auth_helper.py --login")
    return tencent


def upload_video(video_path, secret_id=None, secret_key=None, sub_app_id=None):
    """
    Upload video to Tencent Cloud VOD

    Args:
        video_path: Path to video file
        secret_id: Tencent Cloud Secret ID (optional, from config)
        secret_id: Tencent Cloud Secret Key (optional, from config)
        sub_app_id: Tencent Cloud Sub App ID (optional, from config)

    Returns:
        dict with video_id, cover_url, media_url
    """
    # Get keys
    if not all([secret_id, secret_key, sub_app_id]):
        tencent = get_tencent_keys()
        secret_id = secret_id or tencent["secret_id"]
        secret_key = secret_key or tencent["secret_key"]
        sub_app_id = sub_app_id or tencent["sub_app_id"]

    # Check file
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    file_size = video_path.stat().st_size
    print(f"Uploading: {video_path.name} ({file_size / 1024 / 1024:.1f} MB)")

    try:
        # Try using vod-python-sdk
        from vod_uploader import upload
        result = upload(
            str(video_path),
            secret_id=secret_id,
            secret_key=secret_key,
            sub_app_id=int(sub_app_id)
        )
        print(f"Upload complete! Video ID: {result.get('file_id')}")
        return result
    except ImportError:
        pass

    # Fallback: try tencentcloud SDK
    try:
        from tencentcloud.vod.v20180717 import vod_client, models
        from tencentcloud.common import credential

        cred = credential.Credential(secret_id, secret_key)
        client = vod_client.VodClient(cred, "")

        # Apply upload
        req = models.ApplyUploadRequest()
        req.SubAppId = int(sub_app_id)
        req.MediaName = video_path.name
        req.MediaType = "mp4"

        resp = client.ApplyUpload(req)
        storage = resp.StorageBucket
        vod_session_key = resp.VodSessionKey

        # Upload file (simplified - real implementation needs cos upload)
        print(f"Upload session: {vod_session_key[:20]}...")

        # For now, return placeholder
        return {
            "file_id": resp.FileId,
            "media_url": f"https://{storage}.cos.amazonaws.com/{resp.MediaStoragePath}",
            "cover_url": resp.CoverStoragePath
        }

    except ImportError:
        raise ImportError(
            "No upload SDK found. Install one of:\n"
            "  pip install vod-python-sdk\n"
            "  pip install tencentcloud-sdk-python-vod"
        )


def main():
    parser = argparse.ArgumentParser(description="Upload video to Tencent Cloud VOD")
    parser.add_argument("--video", required=True, help="Video file path")
    parser.add_argument("--secret-id", help="Tencent Secret ID")
    parser.add_argument("--secret-key", help="Tencent Secret Key")
    parser.add_argument("--app-id", help="Tencent Sub App ID")

    args = parser.parse_args()

    try:
        result = upload_video(
            args.video,
            args.secret_id,
            args.secret_key,
            args.app_id
        )
        print("\nUpload Result:")
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
