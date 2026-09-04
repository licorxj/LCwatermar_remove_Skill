---
name: lcwr-watermark-remover
description: QingMu Video Watermark Remover (LCWR). Complete video watermark removal workflow: authentication, Tencent Cloud VOD upload, cloud AI watermark removal, result download. Use when user wants to remove watermarks from videos, needs video watermark removal, or mentions "remove watermark", "video watermark", "LCWR", "qingmu watermark".
---

# LCWR - QingMu Video Watermark Remover

## Overview

Complete video watermark removal tool using QingMu capability platform. Workflow:
1. **Authenticate** - Login to get API Key and Tencent Cloud credentials
2. **Upload** - Upload video to Tencent Cloud VOD
3. **Process** - Submit watermark removal task to cloud AI
4. **Download** - Get watermark-free result

## Quick Start

### First Time Setup

1. Run the tool - browser opens to login page
2. Register/login at https://www.licorxj.online/capability-hub
3. Copy API Key and paste back
4. Start removing watermarks!

### Usage

```bash
# Interactive mode (guided workflow)
python scripts/watermark_remover.py

# With API Key
python scripts/watermark_remover.py --api-key YOUR_KEY

# With video file
python scripts/watermark_remover.py --video path/to/video.mp4

# Environment variable
set LICORXJ_API_KEY=your_key
python scripts/watermark_remover.py --video video.mp4
```

## Core Scripts

### watermark_remover.py - Main Script
Complete watermark removal workflow:
```bash
python scripts/watermark_remover.py --video video.mp4 --api-key KEY
```

### auth_helper.py - Authentication
Manage API Key and Tencent Cloud credentials:
```bash
python scripts/auth_helper.py --login
python scripts/auth_helper.py --show-keys
```

### video_uploader.py - Upload to Tencent Cloud
Upload videos to Tencent Cloud VOD:
```bash
python scripts/video_uploader.py --video video.mp4
```

### hub_client.py - Cloud Processing
Submit and track watermark removal tasks:
```bash
python scripts/hub_client.py --submit --video-id VID
python scripts/hub_client.py --status --request-id RID
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `LICORXJ_API_KEY` | Qingmu platform API Key | Yes (or config file) |
| `FFMPEG_PATH` | Custom ffmpeg path | No |

## Config File

Location: `~/.licorxj/config.json`
```json
{
  "api_key": "your_api_key",
  "tencent_vod_keys": {
    "secret_id": "AKID...",
    "secret_key": "vkRz...",
    "sub_app_id": "1323480989"
  }
}
```

## Workflow Details

### 1. Authentication
- First use: browser opens for registration/login
- API Key saved to config for future use
- Tencent Cloud keys fetched via software ID qm0101

### 2. Video Upload
- Upload to Tencent Cloud VOD
- Get video_id for processing
- Support MP4, AVI, MOV formats

### 3. Cloud Processing
- Submit task with video_id and watermark coordinates
- Poll status until completion
- Automatic retry on failure

### 4. Result Download
- Download processed video
- Save to output directory

## Notes

- API Key required for all operations (prevents abuse)
- Processing time depends on video length
- Credits consumed: ~1.3 points/second
- Minimum charge: 10 seconds

## Resources

### scripts/
- `watermark_remover.py` - Main workflow script
- `auth_helper.py` - Authentication helper
- `video_uploader.py` - Video upload module
- `hub_client.py` - Cloud processing client

### references/
- `api_reference.md` - API documentation
- `workflow_guide.md` - Detailed workflow guide
