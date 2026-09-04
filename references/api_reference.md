# API Reference

## Qingmu Platform (licorxj.online)

### Authentication
- `POST /api/auth/login` - User login
- `POST /api/auth/register` - User registration
- `GET /api/user/info` - Get user info

### Software Data
- `GET /api/software/public/{id}/secure-data` - Get software secure data

### Capability Hub
- `POST /api/capability/invoke` - Invoke capability (watermark removal)
- `GET /api/capability/tasks/{id}` - Get task status

## Tencent Cloud VOD

### Upload
- Use `vod-python-sdk` or `tencentcloud-sdk-python-vod`
- Upload video, get `file_id` and `media_url`

### Key Format
```json
{
  "tencent": {
    "secret_id": "AKID...",
    "secret_key": "vkRz...",
    "sub_app_id": "1323480989"
  }
}
```
