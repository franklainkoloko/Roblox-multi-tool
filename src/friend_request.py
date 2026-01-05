import time
import json
from random import uniform, choice
from threading import Thread
from typing import Tuple, Optional, List
from curl_cffi import Session
from colorama import Fore, Style
from src.utils import RobloxClient, PerformanceTracker, load_resources, format_output, format_retry, safe_print


class FriendRequestClient(RobloxClient):
    def _obtain_csrf_token(self, session: Session, target_user_id: str = "1") -> Optional[str]:
        endpoints = [
            ("POST", f"https://friends.roblox.com/v1/users/{target_user_id}/request-friendship"),
            ("POST", "https://friends.roblox.com/v1/users/1/follow"),
            ("POST", "https://friends.roblox.com/v1/users/1/request-friendship"),
            ("GET", "https://www.roblox.com/home"),
        ]
        
        for method, endpoint in endpoints:
            try:
                if method == "POST":
                    response = session.post(endpoint, timeout=10)
                else:
                    response = session.get(endpoint, timeout=10)
                
                csrf_token = response.headers.get("x-csrf-token")
                if csrf_token:
                    session.headers.update({"x-csrf-token": csrf_token})
                    return csrf_token
            except:
                continue
        
        return None

    def _parse_error_reason(self, response_text: str, status_code: int) -> str:
        if not response_text:
            if status_code == 403:
                return "Forbidden"
            elif status_code == 401:
                return "Unauthorized"
            elif status_code == 404:
                return "User not found"
            elif status_code == 429:
                return "Rate limited"
            else:
                return f"HTTP {status_code}"
        
        try:
            error_data = json.loads(response_text)
            if isinstance(error_data, dict):
                if "errors" in error_data and error_data["errors"]:
                    error_obj = error_data["errors"][0]
                    error_msg = error_obj.get("message", "")
                    if error_msg:
                        return error_msg[:60]
                if "message" in error_data:
                    return error_data["message"][:60]
        except:
            pass
        
        response_lower = response_text.lower()
        if "captcha" in response_lower or "challenge" in response_lower:
            return "Captcha required"
        elif "rate limit" in response_lower or "too many" in response_lower:
            return "Rate limited"
        elif "already" in response_lower or "pending" in response_lower:
            return "Already sent"
        elif "blocked" in response_lower:
            return "User blocked"
        elif "privacy" in response_lower:
            return "Privacy settings"
        
        return response_text[:60]

    def execute_friend_request(self, auth_cookie: str, proxy_addr: str, target_user_id: str) -> Tuple[str, bool, int]:
        client_session = Session(
            impersonate="safari",
            default_headers=True,
            proxy=proxy_addr,
            timeout=15
        )

        client_session.headers.update(self._get_headers())

        api_endpoint = f"https://friends.roblox.com/v1/users/{target_user_id}/request-friendship"
        auth_token = self.token_gen.generate_token("", api_endpoint, "post")
        client_session.headers.update({"x-bound-auth-token": auth_token})
        client_session.headers.update({"content-type": "application/json"})

        try:
            self._setup_session_cookies(auth_cookie, client_session)
            time.sleep(uniform(0.2, 0.5))
            
            csrf = self._obtain_csrf_token(client_session, target_user_id)
            if not csrf:
                client_session.close()
                return ("CSRF failed", False, 0)

            time.sleep(uniform(0.3, 0.8))

            response = client_session.post(api_endpoint, json={}, timeout=15)
            status_code = response.status_code
            response_text = response.text
            client_session.close()

            if status_code == 200:
                return ("SUCCESS", True, status_code)
            else:
                error_reason = self._parse_error_reason(response_text, status_code)
                return (error_reason, False, status_code)
        except Exception as e:
            try:
                client_session.close()
            except:
                pass
            error_msg = str(e)
            if "timeout" in error_msg.lower():
                return ("Timeout", False, 0)
            elif "proxy" in error_msg.lower():
                return ("Proxy failed", False, 0)
            else:
                return (f"Error: {error_msg[:40]}", False, 0)


def process_batch(cookie_batch: List[str], user_id: str, tracker: PerformanceTracker, proxy_pool: List[str]):
    client = FriendRequestClient()
    
    for auth_cookie in cookie_batch:
        max_retries = 3
        retry_count = 0
        succeeded = False
        
        while retry_count < max_retries and not succeeded:
            try:
                selected_proxy = choice(proxy_pool) if proxy_pool else None
                request_start = time.time()
                
                result_msg, success, status_code = client.execute_friend_request(
                    auth_cookie, selected_proxy, user_id
                )
                
                request_time = round(time.time() - request_start, 2)
                
                if success:
                    tracker.increment_success()
                    completed, failed, rate = tracker.get_stats()
                    print(format_output("Friend Request Sent", user_id, request_time, completed, rate, "success"))
                    succeeded = True
                else:
                    retry_count += 1
                    
                    if "already" in result_msg.lower():
                        succeeded = True
                        tracker.increment_success()
                        completed, failed, rate = tracker.get_stats()
                        print(format_output("Friend Request", user_id, request_time, completed, rate, "already"))
                    else:
                        tracker.increment_failure()
                        completed, failed, rate = tracker.get_stats()
                        
                        if retry_count < max_retries:
                            print(format_retry(result_msg, retry_count, max_retries))
                            delay = uniform(1.0, 2.5) * retry_count
                            time.sleep(delay)
                        else:
                            print(format_output("Friend Request", user_id, request_time, completed, rate, "failed"))
                        
            except Exception as e:
                retry_count += 1
                tracker.increment_failure()
                if retry_count < max_retries:
                    time.sleep(uniform(0.5, 1.5))
        
        if not succeeded:
            time.sleep(uniform(0.2, 0.6))


def distribute_items(items: List, num_workers: int) -> List[List]:
    if num_workers <= 0:
        return [items]
    
    chunk_size = len(items) / num_workers
    result = []
    current_pos = 0.0
    
    while current_pos < len(items):
        end_pos = int(current_pos + chunk_size)
        result.append(items[int(current_pos):end_pos])
        current_pos += chunk_size
    
    return result


def main():
    proxy_pool, cookie_pool = load_resources()
    
    if not cookie_pool:
        print(f"{Fore.RED}No cookies found in data/cookies.txt{Style.RESET_ALL}")
        return
    
    try:
        thread_count = int(input(f"{Fore.CYAN}Threads: {Style.RESET_ALL}"))
        target_user = input(f"{Fore.CYAN}User ID: {Style.RESET_ALL}")
    except (ValueError, KeyboardInterrupt):
        return
    
    if thread_count <= 0:
        thread_count = 1
        
    tracker = PerformanceTracker()
    batches = distribute_items(cookie_pool, thread_count)
    worker_threads = []
    
    for batch in batches:
        if batch:
            thread = Thread(
                target=process_batch,
                args=(batch, target_user, tracker, proxy_pool)
            )
            worker_threads.append(thread)
            thread.start()
            time.sleep(uniform(0.1, 0.3))
    
    for thread in worker_threads:
        thread.join()
    
    final_completed, final_failed, final_rate = tracker.get_stats()
    total_attempts = final_completed + final_failed
    success_rate = (final_completed / total_attempts * 100) if total_attempts > 0 else 0
    
    print(f"\n{Fore.CYAN}{'═' * 63}")
    print(f"{Fore.GREEN}Success: {Fore.MAGENTA}{final_completed}{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}|{Style.RESET_ALL} "
          f"{Fore.RED}Failed: {Fore.MAGENTA}{final_failed}{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}|{Style.RESET_ALL} "
          f"{Fore.CYAN}Rate: {Fore.MAGENTA}{success_rate:.1f}%{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}|{Style.RESET_ALL} "
          f"{Fore.MAGENTA}{final_rate}{Style.RESET_ALL}/min")
    print(f"{Fore.CYAN}{'═' * 63}{Style.RESET_ALL}")


if __name__ == "__main__":
    main()