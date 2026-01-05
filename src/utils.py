import time
import hashlib
import base64
from pathlib import Path
from typing import Tuple, List
from colorama import Fore, Style
from curl_cffi import Session
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature


class TokenGenerator:
    
    @staticmethod
    def _to_bytes(text: str) -> bytes:
        return text.encode('utf-8')

    @staticmethod
    def _b64_encode(data: bytes) -> str:
        return base64.b64encode(data).decode('ascii')
    
    def generate_token(self, payload: str, endpoint: str, http_method: str) -> str:
        payload_bytes = payload.encode('utf-8')
        hash_digest = hashlib.sha256(payload_bytes).digest()
        encoded_hash = self._b64_encode(hash_digest)

        current_time = str(int(time.time()))
        key_pair = ec.generate_private_key(ec.SECP256R1(), default_backend())

        sig_data = f"{encoded_hash}|{current_time}|{endpoint}|{http_method.upper()}"
        sig_bytes = key_pair.sign(
            self._to_bytes(sig_data),
            ec.ECDSA(hashes.SHA256())
        )
        r_val, s_val = decode_dss_signature(sig_bytes)
        sig_raw = r_val.to_bytes(32, 'big') + s_val.to_bytes(32, 'big')
        encoded_sig1 = self._b64_encode(sig_raw)

        path_suffix = endpoint.split('.com')[1] if '.com' in endpoint else endpoint
        sig_data2 = f"|{current_time}|{path_suffix}|{http_method.upper()}"
        sig_bytes2 = key_pair.sign(
            self._to_bytes(sig_data2),
            ec.ECDSA(hashes.SHA256())
        )
        r_val2, s_val2 = decode_dss_signature(sig_bytes2)
        sig_raw2 = r_val2.to_bytes(32, 'big') + s_val2.to_bytes(32, 'big')
        encoded_sig2 = self._b64_encode(sig_raw2)

        return f"v1|{encoded_hash}|{current_time}|{encoded_sig1}|{encoded_sig2}"


class RobloxClient:
    
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    ]
    
    def __init__(self):
        self.token_gen = TokenGenerator()
    
    def _get_headers(self) -> dict:
        from random import choice
        return {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'en-US,en;q=0.9',
            'accept-encoding': 'gzip, deflate, br',
            'origin': 'https://www.roblox.com',
            'referer': 'https://www.roblox.com/',
            'user-agent': choice(self.USER_AGENTS),
            'sec-ch-ua': '"Not A(Brand";v="8", "Chromium";v="121", "Google Chrome";v="121"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
        }
    
    def _setup_session_cookies(self, auth_cookie: str, session: Session):
        session.allow_redirects = True
        session.cookies.set('.ROBLOSECURITY', auth_cookie, domain='.roblox.com', path='/', secure=True)
        response = session.get('https://roblox.com', timeout=8)
        session.cookies.update(response.cookies)


class PerformanceTracker:
    
    def __init__(self):
        self.start_time = time.time()
        self.completed = 0
        self.failed = 0
        self._lock = None
        self.print_lock = None
        try:
            from threading import Lock
            self._lock = Lock()
            self.print_lock = Lock()
        except:
            pass
    
    def increment_success(self):
        if self._lock:
            with self._lock:
                self.completed += 1
        else:
            self.completed += 1
    
    def increment_failure(self):
        if self._lock:
            with self._lock:
                self.failed += 1
        else:
            self.failed += 1
    
    def get_stats(self) -> Tuple[int, int, float]:
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            rate = (self.completed / elapsed) * 60
        else:
            rate = 0.0
        return self.completed, self.failed, round(rate, 2)


def load_resources() -> Tuple[List[str], List[str]]:
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    
    proxy_file = data_dir / "proxies.txt"
    cookie_file = data_dir / "cookies.txt"
    
    proxies = []
    if proxy_file.exists():
        with open(proxy_file, 'r', encoding='utf-8') as f:
            proxies = [line.strip() for line in f if line.strip()]
    
    cookies = []
    if cookie_file.exists():
        with open(cookie_file, 'r', encoding='utf-8') as f:
            cookies = [line.strip() for line in f if line.strip()]
    
    return proxies, cookies


def format_output(action: str, target_id: str, request_time: float, 
                  completed: int, rate: float, status: str) -> str:
    colors = {"success": Fore.GREEN, "already": Fore.CYAN, "failed": Fore.RED}
    action_color = colors.get(status, Fore.RED)
    action_text = action if status == "success" else ("Already" if status == "already" else "Failed")
    
    if "Join" in action or "Group" in action:
        target_type = "Group"
    else:
        target_type = "Asset"
    
    purple = Fore.MAGENTA
    white = Fore.WHITE
    reset = Style.RESET_ALL
    
    return (f"[{action_color}{action_text}{reset}] "
            f"{white}{target_type}{reset} {purple}{target_id}{reset} | "
            f"Time: {purple}{request_time:.2f}s{reset} | "
            f"Completed: {purple}{completed}{reset} | "
            f"Rate: {purple}{rate:.1f}{reset}/min")


def format_retry(error_msg: str, retry_count: int, max_retries: int) -> str:
    yellow = Fore.YELLOW
    purple = Fore.MAGENTA
    reset = Style.RESET_ALL
    
    return (f"[{yellow}Retry{reset}] "
            f"{error_msg[:40]:<40} | "
            f"Attempt: {purple}{retry_count}/{max_retries}{reset}")


def safe_print(message: str, tracker=None):
    if tracker and tracker.print_lock:
        with tracker.print_lock:
            print(message, flush=True)
    else:
        print(message, flush=True)