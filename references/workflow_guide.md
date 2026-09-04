# Workflow Guide

## Complete Watermark Removal Process

### 1. First Time Setup
1. Run: `python watermark_remover.py`
2. Browser opens to login page
3. Register/login at https://www.licorxj.online/capability-hub
4. Copy API Key and paste back
5. Tencent Cloud keys fetched automatically

### 2. Remove Watermark
```bash
python watermark_remover.py --video video.mp4
```

The tool will:
1. Check authentication (prompt login if needed)
2. Upload video to Tencent Cloud VOD
3. Submit watermark removal task
4. Wait for cloud processing (poll every 15s)
5. Download result to `video_nosub.mp4`

### 3. With Coordinates
If watermark is in a specific area:
```bash
python watermark_remover.py --video video.mp4 --coords "100,100,300,300"
```

Coords format: "x1,y1,x2,y2" (top-left and bottom-right corners)

### 4. Batch Processing
Process multiple videos:
```bash
for f in *.mp4; do
  python watermark_remover.py --video "$f"
done
```

## Troubleshooting

### "No API Key found"
Run: `python auth_helper.py --login`

### "Tencent Cloud keys not found"
Run: `python auth_helper.py --login` (re-fetches keys)

### Upload fails
Install SDK: `pip install vod-python-sdk`

### Processing timeout
Videos > 30 minutes may take longer. Default timeout: 1 hour.
