# -*- coding: utf-8 -*-
import base64
import hashlib
import json
import logging
import os
import platform
import subprocess
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

import requests

logger = logging.getLogger(__name__)

# 默认后端地址（可被构造参数 base_url 覆盖）
DEFAULT_BASE_URL = "https://www.licorxj.online"


try:
    # 优先使用 pycryptodome（推荐：pip install pycryptodome）
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad, unpad

    _AES_BACKEND = "pycryptodome"

    def _aes_encrypt(plaintext: bytes, key: bytes, iv: bytes) -> bytes:
        cipher = AES.new(key, AES.MODE_CBC, iv)
        return cipher.encrypt(pad(plaintext, AES.block_size))

    def _aes_decrypt(ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
        cipher = AES.new(key, AES.MODE_CBC, iv)
        return unpad(cipher.decrypt(ciphertext), AES.block_size)

except ImportError:  # pragma: no cover - 兼容回退
    try:
        # 回退到 cryptography（pip install cryptography）
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives.padding import PKCS7
        from cryptography.hazmat.backends import default_backend

        _AES_BACKEND = "cryptography"

        def _aes_encrypt(plaintext: bytes, key: bytes, iv: bytes) -> bytes:
            cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
            encryptor = cipher.encryptor()
            padder = PKCS7(algorithms.AES.block_size).padder()
            padded = padder.update(plaintext) + padder.finalize()
            return encryptor.update(padded) + encryptor.finalize()

        def _aes_decrypt(ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
            cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
            decryptor = cipher.decryptor()
            padded = decryptor.update(ciphertext) + decryptor.finalize()
            unpadder = PKCS7(algorithms.AES.block_size).unpadder()
            return unpadder.update(padded) + unpadder.finalize()

    except ImportError:
        _AES_BACKEND = None

        def _aes_encrypt(*args, **kwargs):  # type: ignore
            raise ImportError(
                "AES 解密需要 pycryptodome 或 cryptography 库，请安装：pip install pycryptodome"
            )

        _aes_decrypt = _aes_encrypt  # type: ignore


def _normalize_aes_key(encryption_key: str) -> bytes:
    """将任意长度的 encryption_key 规整为 32 字节 AES 密钥（与服务端 crypto.py 一致）。"""
    if not encryption_key:
        raise ValueError("encryption_key 不能为空")
    raw = encryption_key.encode("utf-8")
    if len(raw) == 32:
        return raw
    if len(raw) > 32:
        return raw[:32]
    return hashlib.sha256(raw).digest()


def _decrypt_secure_data(ciphertext_b64: str, iv_b64: str, encryption_key: str) -> str:
    """解密 secure_data 密文，返回原始明文字符串。"""
    if _AES_BACKEND is None:
        raise ImportError(
            "解密需要 pycryptodome 或 cryptography 库，请安装：pip install pycryptodome"
        )
    key = _normalize_aes_key(encryption_key)
    iv = base64.b64decode(iv_b64)
    ct = base64.b64decode(ciphertext_b64)
    plaintext_bytes = _aes_decrypt(ct, key, iv)
    return plaintext_bytes.decode("utf-8")


class CloudAuthUserClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.user_info: Optional[Dict[str, Any]] = None
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": f"CloudAuthUserClient/1.0 ({platform.system()}; {platform.release()})"
        })

    def _get_headers(self, include_auth: bool = True) -> Dict[str, str]:
        if include_auth and self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    def _handle_response(self, response: requests.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return {"code": response.status_code, "msg": response.text, "data": None}

    def _try_refresh_token(self) -> bool:
        if not self.refresh_token:
            return False
        try:
            response = self.session.post(
                f"{self.base_url}/api/auth/refresh",
                json={"refresh_token": self.refresh_token},
                timeout=self.timeout,
            )
            if response.status_code != 200:
                return False
            token = response.json().get("access_token")
            if not token:
                return False
            self.token = token
            return True
        except (requests.RequestException, ValueError, AttributeError):
            return False

    def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        include_auth: bool = True,
        form_data: bool = False,
        retry: bool = False,
        _network_retries: int = 2,
    ) -> Any:
        request_method = getattr(self.session, method.lower(), None)
        if request_method is None:
            raise ValueError(f"不支持的 HTTP 方法: {method}")
        request_kwargs: Dict[str, Any] = {
            "params": params,
            "headers": self._get_headers(include_auth),
            "timeout": self.timeout,
        }
        if method.upper() in {"POST", "PUT", "PATCH"}:
            request_kwargs["data" if form_data else "json"] = data
        try:
            response = request_method(f"{self.base_url}{endpoint}", **request_kwargs)
        except (requests.exceptions.SSLError, requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            # TLS/连接层异常（如服务器内存压力导致连接被中途关闭、运营商链路抖动），
            # 这类错误多为瞬时，短暂退避后重试即可自愈
            if _network_retries > 0:
                delay = 0.5 * (3 - _network_retries)  # 0.5s / 1.0s
                logger.warning("网络请求异常（%s: %s），%.1f 秒后重试（剩余 %d 次）", type(exc).__name__, exc, delay, _network_retries)
                time.sleep(delay)
                return self._request(method, endpoint, data, params, include_auth, form_data, retry, _network_retries - 1)
            logger.exception("网络请求异常，重试后仍失败")
            raise
        except requests.RequestException:
            logger.exception("网络请求异常")
            raise
        if response.status_code == 401 and include_auth and not retry and self._try_refresh_token():
            return self._request(method, endpoint, data, params, include_auth, form_data, True)
        return self._handle_response(response)

    def _require_login(self) -> Optional[Dict[str, Any]]:
        if self.token:
            return None
        return {"code": 1100, "msg": "未授权，请先登录"}

    def register(
        self,
        username: str,
        password: str,
        email: str,
        phone: Optional[str] = None,
        verification_code: Optional[str] = None,
    ) -> Any:
        data: Dict[str, Any] = {"username": username, "password": password, "email": email}
        if phone:
            data["phone"] = phone
        if verification_code:
            data["verification_code"] = verification_code
        return self._request("POST", "/api/auth/register", data, include_auth=False)

    def send_verification_code(self, email: str) -> Any:
        return self._request("POST", "/api/auth/send-code", {"email": email}, include_auth=False)

    def login(self, username: str, password: str) -> bool:
        try:
            result = self._request(
                "POST",
                "/api/auth/login",
                {"username": username, "password": password,"software_id":"qm0101"},
                include_auth=False,
                form_data=True,
            )
        except requests.RequestException:
            return False
        if not isinstance(result, dict) or "access_token" not in result:
            return False
        self.token = result["access_token"]
        self.refresh_token = result.get("refresh_token")
        self.user_info = self.get_user_info()
        return True

    def logout(self) -> None:
        if self.token:
            try:
                self._request("POST", "/api/auth/logout")
            except requests.RequestException:
                pass
        self.token = None
        self.refresh_token = None
        self.user_info = None

    def send_reset_password_code(self, email: str) -> Any:
        return self._request("POST", "/api/auth/reset-password/send-code", {"email": email}, include_auth=False)

    def reset_password(self, email: str, code: str, new_password: str) -> Any:
        return self._request(
            "POST",
            "/api/auth/reset-password/confirm",
            {"email": email, "code": code, "new_password": new_password},
            include_auth=False,
        )

    def get_user_info(self) -> Optional[Dict[str, Any]]:
        if not self.token:
            return None
        result = self._request("GET", "/api/user/info")
        if isinstance(result, dict) and result.get("code") == 0:
            result = result.get("data")
        if isinstance(result, dict) and result.get("id") is not None:
            self.user_info = result
            return result
        return None

    def edit_user_info(
        self,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        password: Optional[str] = None,
    ) -> Any:
        unauthorized = self._require_login()
        if unauthorized:
            return unauthorized
        data = {key: value for key, value in {"email": email, "phone": phone, "password": password}.items() if value}
        if not data:
            return {"code": 3000, "msg": "请提供要修改的字段"}
        result = self._request("POST", "/api/user/edit", data)
        if isinstance(result, dict) and result.get("id") is not None:
            self.user_info = result
        return result

    def get_user_entitlements(self) -> List[Dict[str, Any]]:
        if not self.token:
            return []
        result = self._request("GET", "/api/user/entitlements")
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and result.get("code") == 0:
            return result.get("data", [])
        return []

    def software_login(self, software_id: str, device_code: Optional[str] = None, device_name: Optional[str] = None) -> Any:
        unauthorized = self._require_login()
        if unauthorized:
            return unauthorized
        return self._request("POST", "/api/user/software/login", {
            "software_id": software_id,
            "device_code": device_code or self.get_machine_code(),
            "device_name": device_name or platform.node(),
        })

    def get_software_entitlement(self, software_id: str, device_code: Optional[str] = None, device_name: Optional[str] = None) -> Any:
        unauthorized = self._require_login()
        if unauthorized:
            return unauthorized
        return self._request("GET", f"/api/user/software/{software_id}/entitlement", params={
            "device_code": device_code or self.get_machine_code(),
            "device_name": device_name or platform.node(),
        })

    def unbind_device(self, software_id: str, device_code: Optional[str] = None) -> Any:
        unauthorized = self._require_login()
        if unauthorized:
            return unauthorized
        result = self._request("POST", f"/api/user/software/{software_id}/unbind", {
            "device_code": device_code or self.get_machine_code(),
        })
        if isinstance(result, dict) and result.get("code") == 0:
            self.logout()
        return result

    def consume_entitlement(
        self,
        software_id: str,
        consume_type: str = "points",
        amount: int = 1,
        reason: str = "consume",
        device_code: Optional[str] = None,
        device_name: Optional[str] = None,
    ) -> Any:
        unauthorized = self._require_login()
        if unauthorized:
            return unauthorized
        return self._request("POST", f"/api/user/entitlements/{software_id}/consume", {
            "consume_type": consume_type,
            "amount": amount,
            "reason": reason,
            "device_code": device_code or self.get_machine_code(),
            "device_name": device_name or platform.node(),
        })

    def get_github_oauth_url(self) -> Optional[Dict[str, Any]]:
        result = self._request("GET", "/api/auth/oauth/github/authorize", include_auth=False)
        return result.get("data") if isinstance(result, dict) and result.get("code") == 0 else None

    def get_wechat_oauth_url(self) -> Optional[Dict[str, Any]]:
        result = self._request("GET", "/api/auth/oauth/wechat/authorize", include_auth=False)
        return result.get("data") if isinstance(result, dict) and result.get("code") == 0 else None

    def verify_card(self, card_code: str) -> Any:
        if not self.token:
            return None
        return self._request("POST", "/api/card/verify", {"code": card_code})

    def verify_card_advanced(self, card_code: str, device_code: Optional[str] = None, device_name: Optional[str] = None) -> Any:
        if not self.token:
            return None
        return self._request("POST", "/api/card/verify-advanced", {
            "code": card_code,
            "device_code": device_code or self.get_machine_code(),
            "device_name": device_name or platform.node(),
        })

    def get_machine_code(self) -> str:
        machine_id = ""
        try:
            if platform.system() == "Windows":
                output = subprocess.check_output("wmic csproduct get uuid", shell=True).decode().split()
                if len(output) >= 2:
                    machine_id = output[1]
            elif platform.system() == "Linux":
                for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
                    if os.path.exists(path):
                        with open(path, "r") as file:
                            machine_id = file.read().strip()
                        break
            elif platform.system() == "Darwin":
                output = subprocess.check_output("ioreg -rd1 -c IOPlatformExpertDevice | grep IOPlatformUUID", shell=True).decode()
                machine_id = output.split("=")[-1].strip().replace('"', "")
        except (OSError, subprocess.SubprocessError):
            pass
        if not machine_id or machine_id == "unknown":
            machine_id = f"{uuid.getnode():012x}"
        return hashlib.sha256(machine_id.encode()).hexdigest()[:32]

    def get_public_software_list(self, skip: int = 0, limit: int = 20) -> Any:
        return self._request("GET", "/api/software/public/list", params={"skip": skip, "limit": limit}, include_auth=False)

    def get_my_software_list(self) -> Any:
        unauthorized = self._require_login()
        return unauthorized or self._request("GET", "/api/software/my/list")

    def get_software_detail(self, software_id: str) -> Optional[Dict[str, Any]]:
        result = self._request("GET", f"/api/software/public/{software_id}", include_auth=False)
        if isinstance(result, dict) and result.get("code") == 0:
            return result.get("data")
        return result if isinstance(result, dict) and result.get("id") is not None else None

    def get_software_secure_data(
        self,
        software_id: Union[str, int],
        encryption_key: Optional[str] = None,
        device_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取软件专有 JSON 数据（自动解密）。

        本方法走公开接口，无需登录即可调用。是否下发数据取决于软件是否
        配置了 secure_data；是否加密取决于软件是否配置了 encryption_key。

        流程：
            1. 调用后端 `GET /api/software/public/{software_id}/secure-data`
               （公开接口，无需登录）
            2. 若服务端返回密文（has_data=True, encrypted=True），使用 `encryption_key` 做
               AES-256-CBC 解密得到原始 JSON 字符串，再解析为 dict 返回。
            3. 若服务端返回明文（未配置 encryption_key），直接解析 plaintext 字段。
            4. 若无数据（has_data=False），返回空 dict。

        Args:
            software_id: 软件标识（software_id 字符串或数据库 ID）
            encryption_key: 软件 encryption_key（开发者后台配置）。若为 None 且服务端
                            返回密文，则本方法无法解密，会返回带 `need_encryption_key=True`
                            标志的提示信息。
            device_code: 设备码（可选，保留参数以兼容老调用方；公开接口当前不校验设备）

        Returns:
            dict，包含以下字段：
              - has_data (bool): 软件是否配置了 secure_data
              - encrypted (bool): 是否加密传输
              - data (dict | None): 解密后的原始 JSON 对象（has_data=False 时为 None）
              - raw (str | None): 解密后的原始 JSON 字符串
              - error (str | None): 错误信息（如有）
              - need_encryption_key (bool): 服务端加密但未传入 encryption_key
        """
        params = {}
        if device_code:
            params["device_code"] = device_code

        result = self._request(
            "GET",
            f"/api/software/public/{software_id}/secure-data",
            params=params,
            include_auth=False,  # 公开接口，无需登录
        )

        # 兼容 {code, msg, data} 包装
        if isinstance(result, dict) and result.get("code") == 0:
            data = result.get("data") or {}
        elif isinstance(result, dict) and "has_data" in result:
            data = result
        else:
            return {
                "has_data": False,
                "encrypted": False,
                "data": None,
                "raw": None,
                "error": f"接口返回异常：{result}",
            }

        has_data = bool(data.get("has_data"))
        if not has_data:
            return {
                "has_data": False,
                "encrypted": False,
                "data": None,
                "raw": None,
                "error": None,
            }

        # 服务端明文下发（未配置 encryption_key）
        if not data.get("encrypted"):
            plaintext = data.get("plaintext")
            if not plaintext:
                return {
                    "has_data": True,
                    "encrypted": False,
                    "data": None,
                    "raw": None,
                    "error": "服务端返回空明文",
                }
            try:
                return {
                    "has_data": True,
                    "encrypted": False,
                    "data": json.loads(plaintext),
                    "raw": plaintext,
                    "error": None,
                }
            except json.JSONDecodeError as e:
                return {
                    "has_data": True,
                    "encrypted": False,
                    "data": None,
                    "raw": plaintext,
                    "error": f"明文 JSON 解析失败：{e}",
                }

        # 服务端密文下发
        ciphertext_b64 = data.get("ciphertext")
        iv_b64 = data.get("iv")
        if not ciphertext_b64 or not iv_b64:
            return {
                "has_data": True,
                "encrypted": True,
                "data": None,
                "raw": None,
                "error": "服务端返回密文但缺少 ciphertext 或 iv",
            }

        if not encryption_key:
            return {
                "has_data": True,
                "encrypted": True,
                "data": None,
                "raw": None,
                "error": "服务端已加密但未传入 encryption_key",
                "need_encryption_key": True,
            }

        try:
            plaintext = _decrypt_secure_data(ciphertext_b64, iv_b64, encryption_key)
        except Exception as e:
            return {
                "has_data": True,
                "encrypted": True,
                "data": None,
                "raw": None,
                "error": f"解密失败（密钥错误或密文损坏）：{e}",
            }

        try:
            parsed = json.loads(plaintext)
        except json.JSONDecodeError as e:
            return {
                "has_data": True,
                "encrypted": True,
                "data": None,
                "raw": plaintext,
                "error": f"解密成功但 JSON 解析失败：{e}",
            }

        return {
            "has_data": True,
            "encrypted": True,
            "data": parsed,
            "raw": plaintext,
            "error": None,
        }

    def check_update(self, software_id: str) -> Optional[Dict[str, Any]]:
        result = self._request("GET", "/api/version/latest", params={"software_id": software_id}, include_auth=False)
        return result if isinstance(result, dict) and result.get("version") else None

    def get_version_list(self, software_id: str) -> List[Dict[str, Any]]:
        result = self._request("GET", "/api/version/public/list", params={"software_id": software_id}, include_auth=False)
        return result if isinstance(result, list) else result.get("versions", []) if isinstance(result, dict) else []

    def get_announcements(self, limit: int = 10) -> List[Dict[str, Any]]:
        result = self._request("GET", "/api/announcement/public/list", params={"limit": limit}, include_auth=False)
        return result if isinstance(result, list) else result.get("announcements", []) if isinstance(result, dict) else []

    def get_latest_announcements(self, software_id: Optional[str] = None) -> List[Dict[str, Any]]:
        params = {"software_id": software_id} if software_id else {}
        result = self._request("GET", "/api/announcement/latest", params=params, include_auth=False)
        return result if isinstance(result, list) else result.get("announcements", []) if isinstance(result, dict) else []

    def get_packages(self, software_id: Optional[str] = None) -> Any:
        params = {"software_id": software_id} if software_id else {}
        return self._request("GET", "/api/commerce/packages", params=params, include_auth=False)

    def get_payment_channels(self) -> Any:
        return self._request("GET", "/api/commerce/payment/channels")

    def create_order(self, package_id: int) -> Any:
        unauthorized = self._require_login()
        return unauthorized or self._request("POST", "/api/commerce/orders", {"package_id": package_id})

    def pay_order(self, order_no: str, pay_channel: str = "mock") -> Any:
        unauthorized = self._require_login()
        return unauthorized or self._request("POST", f"/api/commerce/orders/{order_no}/pay", {"pay_channel": pay_channel})

    def get_my_orders(self) -> Any:
        unauthorized = self._require_login()
        return unauthorized or self._request("GET", "/api/commerce/orders/my")

    def get_order_status(self, order_no: str) -> Any:
        unauthorized = self._require_login()
        return unauthorized or self._request("GET", f"/api/commerce/orders/{order_no}/status")

    def get_order_detail(self, order_no: str) -> Any:
        unauthorized = self._require_login()
        return unauthorized or self._request("GET", f"/api/commerce/orders/{order_no}")

    def close_order(self, order_no: str) -> Any:
        unauthorized = self._require_login()
        return unauthorized or self._request("POST", f"/api/commerce/orders/{order_no}/close")

    def is_logged_in(self) -> bool:
        return self.token is not None

    def get_token(self) -> Optional[str]:
        return self.token

    def set_token(self, token: str, refresh_token: Optional[str] = None) -> None:
        self.token = token
        self.refresh_token = refresh_token
        self.user_info = self.get_user_info()
