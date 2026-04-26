import json
import os
import time
import datetime
import hashlib
import hmac
import urllib.error
import urllib.request
from urllib.parse import urlparse


def _minified_json(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _strip_code_fences(text):
    stripped = text.strip()
    if stripped.startswith("```"):
        # Remove the first fence line and last fence line if present
        lines = stripped.splitlines()
        if len(lines) >= 2 and lines[-1].strip().startswith("```"):
            return "\n".join(lines[1:-1]).strip()
    return stripped


def _extract_first_json_object(text):
    text = _strip_code_fences(text)
    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    snippet = text[start : end + 1]
    try:
        return json.loads(snippet)
    except Exception:
        return None


def _to_int(value):
    try:
        return int(value)
    except Exception:
        return None


def _normalize_usage(prompt_tokens=None, completion_tokens=None, total_tokens=None):
    pt = _to_int(prompt_tokens)
    ct = _to_int(completion_tokens)
    tt = _to_int(total_tokens)
    if tt is None and (pt is not None or ct is not None):
        tt = (pt or 0) + (ct or 0)
    if pt is None and ct is None and tt is None:
        return None
    return {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tt}


class OpenAIChatCompletionsClient:
    """
    Minimal OpenAI-compatible Chat Completions HTTP client.
    Uses only the Python standard library (no external dependencies).
    """

    def __init__(
        self,
        api_key,
        model,
        api_base="https://api.openai.com/v1",
        timeout_s=30,
        temperature=0.2,
        max_tokens=300,
        json_response_format=False,
        log_dir=None,
    ):
        self.api_key = api_key
        self.model = model
        self.api_base = api_base.rstrip("/")
        self.timeout_s = timeout_s
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.json_response_format = json_response_format
        self.log_dir = log_dir

    @classmethod
    def from_env(cls):
        api_key = (os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY") or "").strip()
        model = os.getenv("OPENAI_MODEL") or os.getenv("LLM_MODEL")
        api_base = os.getenv("OPENAI_API_BASE") or os.getenv("LLM_API_BASE") or "https://api.openai.com/v1"
        timeout_s = float(os.getenv("LLM_TIMEOUT_S") or 30)
        temperature = float(os.getenv("LLM_TEMPERATURE") or 0.2)
        max_tokens = int(os.getenv("LLM_MAX_TOKENS") or 300)
        json_response_format = (os.getenv("LLM_JSON_RESPONSE_FORMAT") or "").strip().lower() in ("1", "true", "yes")
        log_dir = os.getenv("LLM_LOG_DIR") or None
        if not model:
            return None
        return cls(
            api_key=api_key,
            model=model,
            api_base=api_base,
            timeout_s=timeout_s,
            temperature=temperature,
            max_tokens=max_tokens,
            json_response_format=json_response_format,
            log_dir=log_dir,
        )

    def _log(self, payload):
        if not self.log_dir:
            return
        try:
            os.makedirs(self.log_dir, exist_ok=True)
            file_path = os.path.join(self.log_dir, f"llm_log_{os.getpid()}.jsonl")
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(_minified_json(payload) + "\n")
        except Exception:
            # Logging should never break the simulation.
            return

    def chat_json(self, system_prompt, user_payload):
        url = f"{self.api_base}/chat/completions"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _minified_json(user_payload)},
        ]

        body = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self.json_response_format:
            # Supported by some OpenAI-compatible servers; safe to disable via env.
            body["response_format"] = {"type": "json_object"}

        data = json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method="POST",
        )

        started = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            elapsed_ms = int((time.time() - started) * 1000)
            parsed = json.loads(raw)
            content = (
                parsed.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            result = _extract_first_json_object(content)
            usage_raw = parsed.get("usage")
            usage = None
            if isinstance(usage_raw, dict):
                usage = _normalize_usage(
                    prompt_tokens=usage_raw.get("prompt_tokens"),
                    completion_tokens=usage_raw.get("completion_tokens"),
                    total_tokens=usage_raw.get("total_tokens"),
                )
            self._log(
                {
                    "t_ms": elapsed_ms,
                    "request": {"system": system_prompt, "user": user_payload},
                    "raw_content": content,
                    "parsed_json": result,
                    "usage": usage,
                }
            )
            return result
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode("utf-8", errors="replace")
            except Exception:
                detail = ""
            self._log(
                {
                    "error": "HTTPError",
                    "status": getattr(e, "code", None),
                    "detail": detail,
                    "request": {"system": system_prompt, "user": user_payload},
                }
            )
            return None
        except Exception as e:
            self._log(
                {
                    "error": "Exception",
                    "detail": repr(e),
                    "request": {"system": system_prompt, "user": user_payload},
                }
            )
            return None


class OllamaChatClient:
    """
    Native Ollama client (http://localhost:11434/api/chat).

    Env:
    - OLLAMA_BASE_URL (default http://localhost:11434)
    - OLLAMA_MODEL (or LLM_MODEL)
    - LLM_TIMEOUT_S, LLM_TEMPERATURE, LLM_MAX_TOKENS
    - LLM_JSON_RESPONSE_FORMAT=1 enables Ollama's `format: "json"`.
    - LLM_LOG_DIR optional.
    """

    def __init__(
        self,
        model,
        base_url="http://localhost:11434",
        timeout_s=30,
        temperature=0.2,
        max_tokens=300,
        json_response_format=False,
        log_dir=None,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.json_response_format = json_response_format
        self.log_dir = log_dir

    @classmethod
    def from_env(cls):
        model = os.getenv("OLLAMA_MODEL") or os.getenv("LLM_MODEL")
        base_url = os.getenv("OLLAMA_BASE_URL") or os.getenv("LLM_API_BASE") or "http://localhost:11434"
        timeout_s = float(os.getenv("LLM_TIMEOUT_S") or 30)
        temperature = float(os.getenv("LLM_TEMPERATURE") or 0.2)
        max_tokens = int(os.getenv("LLM_MAX_TOKENS") or 300)
        json_response_format = (os.getenv("LLM_JSON_RESPONSE_FORMAT") or "").strip().lower() in ("1", "true", "yes")
        log_dir = os.getenv("LLM_LOG_DIR") or None
        if not model:
            return None
        return cls(
            model=model,
            base_url=base_url,
            timeout_s=timeout_s,
            temperature=temperature,
            max_tokens=max_tokens,
            json_response_format=json_response_format,
            log_dir=log_dir,
        )

    def _log(self, payload):
        if not self.log_dir:
            return
        try:
            os.makedirs(self.log_dir, exist_ok=True)
            file_path = os.path.join(self.log_dir, f"llm_log_{os.getpid()}.jsonl")
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(_minified_json(payload) + "\n")
        except Exception:
            return

    def chat_json(self, system_prompt, user_payload):
        url = f"{self.base_url}/api/chat"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _minified_json(user_payload)},
        ]

        body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }
        if self.json_response_format:
            body["format"] = "json"

        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        started = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            elapsed_ms = int((time.time() - started) * 1000)
            parsed = json.loads(raw)
            content = parsed.get("message", {}).get("content", "")
            result = _extract_first_json_object(content)
            usage = _normalize_usage(
                prompt_tokens=parsed.get("prompt_eval_count"),
                completion_tokens=parsed.get("eval_count"),
                total_tokens=None,
            )
            self._log(
                {
                    "t_ms": elapsed_ms,
                    "request": {"system": system_prompt, "user": user_payload},
                    "raw_content": content,
                    "parsed_json": result,
                    "usage": usage,
                }
            )
            return result
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode("utf-8", errors="replace")
            except Exception:
                detail = ""
            self._log(
                {
                    "error": "HTTPError",
                    "status": getattr(e, "code", None),
                    "detail": detail,
                    "request": {"system": system_prompt, "user": user_payload},
                }
            )
            return None
        except Exception as e:
            self._log(
                {
                    "error": "Exception",
                    "detail": repr(e),
                    "request": {"system": system_prompt, "user": user_payload},
                }
            )
            return None


def _aws_sign(key, msg):
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _aws_sha256_hex(data_bytes):
    return hashlib.sha256(data_bytes).hexdigest()


class BedrockConverseClient:
    """
    AWS Bedrock Runtime client using the Converse API (SigV4, standard library only).

    Env (required):
    - AWS_ACCESS_KEY_ID
    - AWS_SECRET_ACCESS_KEY
    - AWS_REGION (or BEDROCK_REGION)
    - BEDROCK_MODEL_ID (or LLM_MODEL)
    Optional:
    - AWS_SESSION_TOKEN
    - LLM_TIMEOUT_S, LLM_TEMPERATURE, LLM_MAX_TOKENS
    - LLM_LOG_DIR
    """

    def __init__(
        self,
        access_key,
        secret_key,
        session_token,
        region,
        model_id,
        timeout_s=30,
        temperature=0.2,
        max_tokens=300,
        log_dir=None,
    ):
        self.access_key = access_key
        self.secret_key = secret_key
        self.session_token = session_token
        self.region = region
        self.model_id = model_id
        self.timeout_s = timeout_s
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.log_dir = log_dir

    @classmethod
    def from_env(cls):
        access_key = (os.getenv("AWS_ACCESS_KEY_ID") or "").strip()
        secret_key = (os.getenv("AWS_SECRET_ACCESS_KEY") or "").strip()
        session_token = (os.getenv("AWS_SESSION_TOKEN") or "").strip() or None
        region = (os.getenv("AWS_REGION") or os.getenv("BEDROCK_REGION") or "").strip()
        model_id = (os.getenv("BEDROCK_MODEL_ID") or os.getenv("LLM_MODEL") or "").strip()
        timeout_s = float(os.getenv("LLM_TIMEOUT_S") or 30)
        temperature = float(os.getenv("LLM_TEMPERATURE") or 0.2)
        max_tokens = int(os.getenv("LLM_MAX_TOKENS") or 300)
        log_dir = os.getenv("LLM_LOG_DIR") or None

        if not (access_key and secret_key and region and model_id):
            return None

        return cls(
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token,
            region=region,
            model_id=model_id,
            timeout_s=timeout_s,
            temperature=temperature,
            max_tokens=max_tokens,
            log_dir=log_dir,
        )

    def _log(self, payload):
        if not self.log_dir:
            return
        try:
            os.makedirs(self.log_dir, exist_ok=True)
            file_path = os.path.join(self.log_dir, f"llm_log_{os.getpid()}.jsonl")
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(_minified_json(payload) + "\n")
        except Exception:
            return

    def _sigv4_headers(self, url, body_bytes):
        parsed = urlparse(url)
        host = parsed.netloc
        canonical_uri = parsed.path or "/"

        now = datetime.datetime.utcnow()
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")

        payload_hash = _aws_sha256_hex(body_bytes)

        headers = {
            "host": host,
            "content-type": "application/json",
            "x-amz-date": amz_date,
            "x-amz-content-sha256": payload_hash,
        }
        if self.session_token:
            headers["x-amz-security-token"] = self.session_token

        signed_headers = ";".join(sorted(headers.keys()))
        canonical_headers = "".join(f"{k}:{headers[k]}\n" for k in sorted(headers.keys()))

        canonical_request = "\n".join(
            [
                "POST",
                canonical_uri,
                "",
                canonical_headers,
                signed_headers,
                payload_hash,
            ]
        )

        algorithm = "AWS4-HMAC-SHA256"
        credential_scope = f"{date_stamp}/{self.region}/bedrock-runtime/aws4_request"
        string_to_sign = "\n".join(
            [
                algorithm,
                amz_date,
                credential_scope,
                _aws_sha256_hex(canonical_request.encode("utf-8")),
            ]
        )

        k_date = _aws_sign(("AWS4" + self.secret_key).encode("utf-8"), date_stamp)
        k_region = hmac.new(k_date, self.region.encode("utf-8"), hashlib.sha256).digest()
        k_service = hmac.new(k_region, b"bedrock-runtime", hashlib.sha256).digest()
        k_signing = hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()
        signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        authorization = (
            f"{algorithm} Credential={self.access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )

        final_headers = {
            "Content-Type": "application/json",
            "X-Amz-Date": amz_date,
            "X-Amz-Content-Sha256": payload_hash,
            "Authorization": authorization,
        }
        if self.session_token:
            final_headers["X-Amz-Security-Token"] = self.session_token
        return final_headers

    def chat_json(self, system_prompt, user_payload):
        url = f"https://bedrock-runtime.{self.region}.amazonaws.com/model/{self.model_id}/converse"

        body = {
            "system": [{"text": system_prompt}],
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": _minified_json(user_payload)}],
                }
            ],
            "inferenceConfig": {
                "temperature": self.temperature,
                "maxTokens": self.max_tokens,
            },
        }

        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = self._sigv4_headers(url, data)
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        started = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            elapsed_ms = int((time.time() - started) * 1000)
            parsed = json.loads(raw)

            content_blocks = (
                parsed.get("output", {})
                .get("message", {})
                .get("content", [])
            )
            text = ""
            if isinstance(content_blocks, list) and content_blocks:
                first = content_blocks[0]
                if isinstance(first, dict):
                    text = first.get("text", "") or ""

            result = _extract_first_json_object(text)
            usage_raw = parsed.get("usage")
            usage = None
            if isinstance(usage_raw, dict):
                usage = _normalize_usage(
                    prompt_tokens=usage_raw.get("inputTokens"),
                    completion_tokens=usage_raw.get("outputTokens"),
                    total_tokens=usage_raw.get("totalTokens"),
                )
            self._log(
                {
                    "t_ms": elapsed_ms,
                    "request": {"system": system_prompt, "user": user_payload},
                    "raw_text": text,
                    "parsed_json": result,
                    "usage": usage,
                }
            )
            return result
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode("utf-8", errors="replace")
            except Exception:
                detail = ""
            self._log(
                {
                    "error": "HTTPError",
                    "status": getattr(e, "code", None),
                    "detail": detail,
                    "request": {"system": system_prompt, "user": user_payload},
                }
            )
            return None
        except Exception as e:
            self._log(
                {
                    "error": "Exception",
                    "detail": repr(e),
                    "request": {"system": system_prompt, "user": user_payload},
                }
            )
            return None


def create_chat_client_from_env():
    provider = (os.getenv("LLM_PROVIDER") or "").strip().lower()
    if provider in ("ollama",):
        return OllamaChatClient.from_env()
    if provider in ("bedrock", "aws", "aws-bedrock"):
        return BedrockConverseClient.from_env()
    # Default: OpenAI-compatible Chat Completions
    return OpenAIChatCompletionsClient.from_env()
