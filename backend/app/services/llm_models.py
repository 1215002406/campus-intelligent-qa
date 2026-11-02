import base64
import hashlib
import json
from datetime import datetime, timezone
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

from app.core.config import Settings


class LLMModelService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._active_file = settings.model_cache_dir / "active-llm.json"
        self._remote_file = settings.model_cache_dir / "remote-llm.json"
        self._load_remote_profile()
        self._load_active_provider()

    def status(self) -> dict:
        return {
            "active_provider": self.settings.llm_provider,
            "profiles": [
                {
                    "id": "local",
                    "label": "本地 Qwen3.8-27B",
                    "configured": self._local_configured(),
                    "active": self.settings.llm_provider == "local",
                    "base_url": self.settings.llm_local_base_url,
                    "model": self.settings.llm_local_model,
                },
                {
                    "id": "remote",
                    "label": "远程回答模型",
                    "configured": self._remote_configured(),
                    "active": self.settings.llm_provider == "remote",
                    "base_url": self.settings.llm_remote_base_url,
                    "model": self.settings.llm_remote_model,
                },
            ],
        }

    def switch(self, provider: str) -> dict:
        if provider == "local" and not self._local_configured():
            raise RuntimeError("本地回答模型配置不完整")
        if provider == "remote" and not self._remote_configured():
            raise RuntimeError("请先在 backend/.env 中填写远程模型地址、模型名称和 API Key")
        self.settings.llm_provider = provider
        self.settings.model_cache_dir.mkdir(parents=True, exist_ok=True)
        self._active_file.write_text(
            json.dumps({
                "provider": provider,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return self.status()

    def configure_remote(self, *, base_url: str, model: str, api_key: str | None) -> dict:
        normalized_url = base_url.strip().rstrip("/")
        parsed = urlparse(normalized_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("远程模型地址必须是有效的 HTTP 或 HTTPS URL")
        normalized_model = model.strip()
        if not normalized_model:
            raise ValueError("远程模型名称不能为空")
        key = (api_key or "").strip() or self.settings.llm_remote_api_key.get_secret_value()
        if not key:
            raise ValueError("远程模型 API Key 不能为空")

        self.settings.model_cache_dir.mkdir(parents=True, exist_ok=True)
        self._remote_file.write_text(
            json.dumps({
                "base_url": normalized_url,
                "model": normalized_model,
                "api_key": self._encrypt(key),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.settings.llm_remote_base_url = normalized_url
        self.settings.llm_remote_model = normalized_model
        self.settings.llm_remote_api_key = SecretStr(key)
        return self.status()

    def _load_active_provider(self) -> None:
        try:
            data = json.loads(self._active_file.read_text(encoding="utf-8"))
            provider = data.get("provider")
            if provider in {"local", "remote"}:
                if provider == "remote" and not self._remote_configured():
                    return
                self.settings.llm_provider = provider
        except (FileNotFoundError, OSError, ValueError):
            return

    def _load_remote_profile(self) -> None:
        try:
            data = json.loads(self._remote_file.read_text(encoding="utf-8"))
            base_url = str(data.get("base_url", "")).strip()
            model = str(data.get("model", "")).strip()
            encrypted_key = str(data.get("api_key", ""))
            if not base_url or not model or not encrypted_key:
                return
            api_key = self._decrypt(encrypted_key)
            self.settings.llm_remote_base_url = base_url
            self.settings.llm_remote_model = model
            self.settings.llm_remote_api_key = SecretStr(api_key)
        except (FileNotFoundError, OSError, ValueError, InvalidToken, KeyError):
            return

    def _fernet(self) -> Fernet:
        secret = self.settings.jwt_secret_key.get_secret_value().encode("utf-8")
        key = base64.urlsafe_b64encode(hashlib.sha256(b"campus-llm-profile:" + secret).digest())
        return Fernet(key)

    def _encrypt(self, value: str) -> str:
        return self._fernet().encrypt(value.encode("utf-8")).decode("ascii")

    def _decrypt(self, value: str) -> str:
        return self._fernet().decrypt(value.encode("ascii")).decode("utf-8")

    def _local_configured(self) -> bool:
        return bool(self.settings.llm_local_base_url and self.settings.llm_local_model)

    def _remote_configured(self) -> bool:
        return bool(
            self.settings.llm_remote_base_url
            and self.settings.llm_remote_model
            and self.settings.llm_remote_api_key.get_secret_value()
        )
