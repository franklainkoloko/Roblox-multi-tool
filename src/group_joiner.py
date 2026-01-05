import time
import json
from random import uniform
from threading import Thread
from typing import Tuple, Optional
from queue import Queue, Empty
from curl_cffi import Session
from colorama import Fore, Style
from src.utils import RobloxClient, PerformanceTracker, load_resources, format_output, format_retry, safe_print


class GroupClient(RobloxClient):
    def _obtain_csrf_token(self, session: Session, group_id: str = "1") -> Optional[str]:
        endpoints = [
            ("POST", f"https://groups.roblox.com/v1/groups/{group_id}/users"),
            ("POST", "https://friends.roblox.com/v1/users/1/follow"),
        ]
        
        for method, endpoint in endpoints:
            try:
                if method == "POST":
                    response = session.post(endpoint, timeout=8)
                else:
                    response = session.get(endpoint, timeout=8)
                
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
                return "Group not found"
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
                        return error_msg[:50]
                if "message" in error_data:
                    return error_data["message"][:50]
        except:
            pass
        
        response_lower = response_text.lower()
        if "captcha" in response_lower:
            return "Captcha"
        elif "rate limit" in response_lower:
            return "Rate limited"
        elif "already" in response_lower:
            return "Already member"
        elif "requirement" in response_lower:
            return "Requirements not met"
        
        return response_text[:50]

    def execute_join(self, auth_cookie: str, proxy_addr: str, target_group_id: str) -> Tuple[str, bool, int]:
        client_session = Session(
            impersonate="safari",
            default_headers=True,
            proxy=proxy_addr,
            timeout=12
        )

        client_session.headers.update(self._get_headers())

        api_endpoint = f"https://groups.roblox.com/v1/groups/{target_group_id}/users"
        auth_token = self.token_gen.generate_token("", api_endpoint, "post")
        client_session.headers.update({"x-bound-auth-token": auth_token})

        try:
            self._setup_session_cookies(auth_cookie, client_session)
            
            csrf = self._obtain_csrf_token(client_session, target_group_id)
            if not csrf:
                client_session.close()
                return ("CSRF failed", False, 0)

            response = client_session.post(api_endpoint, timeout=10)
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
                return (f"Error: {error_msg[:30]}", False, 0)


def worker_thread(worker_id: int, cookie_queue: Queue, group_id: str, tracker: PerformanceTracker, 
                  proxy_pool: list, running: list):
    client = GroupClient()
    proxy_index = worker_id % len(proxy_pool) if proxy_pool else 0
    
    while running[0]:
        try:
            auth_cookie = cookie_queue.get_nowait()
        except Empty:
            break
        
        max_retries = 2
        retry_count = 0
        succeeded = False
        
        while retry_count < max_retries and not succeeded and running[0]:
            try:
                selected_proxy = proxy_pool[proxy_index] if proxy_pool else None
                request_start = time.time()
                
                result_msg, success, status_code = client.execute_join(
                    auth_cookie, selected_proxy, group_id
                )
                
                request_time = round(time.time() - request_start, 2)
                
                if success:
                    tracker.increment_success()
                    completed, failed, rate = tracker.get_stats()
                    safe_print(format_output("Joined", group_id, request_time, completed, rate, "success"), tracker)
                    succeeded = True
                else:
                    retry_count += 1
                    
                    if "already" in result_msg.lower():
                        succeeded = True
                        tracker.increment_success()
                        completed, failed, rate = tracker.get_stats()
                        safe_print(format_output("Join", group_id, request_time, completed, rate, "already"), tracker)
                    else:
                        tracker.increment_failure()
                        completed, failed, rate = tracker.get_stats()
                        
                        if retry_count < max_retries:
                            safe_print(format_retry(result_msg, retry_count, max_retries), tracker)
                            time.sleep(uniform(0.5, 1.0))
                            proxy_index = (proxy_index + 1) % len(proxy_pool) if proxy_pool else 0
                        else:
                            safe_print(format_output("Join", group_id, request_time, completed, rate, "failed"), tracker)
                        
            except Exception as e:
                retry_count += 1
                tracker.increment_failure()
                if retry_count < max_retries:
                    time.sleep(uniform(0.3, 0.8))
        
        cookie_queue.task_done()
        time.sleep(uniform(0.05, 0.15))


def main():
    proxy_pool, cookie_pool = load_resources()
    
    if not cookie_pool:
        print(f"{Fore.RED}No cookies found in data/cookies.txt{Style.RESET_ALL}")
        return
    
    try:
        thread_count = int(input(f"{Fore.CYAN}Threads: {Style.RESET_ALL}"))
        target_group = input(f"{Fore.CYAN}Group ID: {Style.RESET_ALL}")
    except (ValueError, KeyboardInterrupt):
        return
    
    if thread_count <= 0:
        thread_count = 1
        
    cookie_queue = Queue()
    for cookie in cookie_pool:
        cookie_queue.put(cookie)
    
    tracker = PerformanceTracker()
    running = [True]
    worker_threads = []
    
    for i in range(thread_count):
        thread = Thread(
            target=worker_thread,
            args=(i, cookie_queue, target_group, tracker, proxy_pool, running),
            daemon=True
        )
        worker_threads.append(thread)
        thread.start()
        time.sleep(0.02)
    
    try:
        cookie_queue.join()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Stopping...{Style.RESET_ALL}")
        running[0] = False
    
    for thread in worker_threads:
        thread.join(timeout=3)
    
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