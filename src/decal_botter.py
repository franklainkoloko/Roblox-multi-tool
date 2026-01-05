import time
from threading import Thread
from queue import Queue, Empty
from random import uniform
from curl_cffi import requests
from colorama import Fore, Style
from src.utils import PerformanceTracker, load_resources, format_output


class DecalClient:
    def create_session(self, proxy):
        session = requests.Session(
            impersonate="chrome110",
            proxy=proxy,
            timeout=15
        )
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })
        return session
    
    def get_csrf_token(self, session, cookie):
        try:
            session.cookies.set('.ROBLOSECURITY', cookie, domain='.roblox.com')
            response = session.post('https://auth.roblox.com/v2/logout', timeout=10)
            token = response.headers.get('x-csrf-token')
            if token:
                return token
            response = session.post('https://auth.roblox.com/v1/logout', timeout=10)
            return response.headers.get('x-csrf-token')
        except Exception:
            return None
    
    def get_product_info(self, session, asset_id, cookie):
        try:
            session.cookies.set('.ROBLOSECURITY', cookie, domain='.roblox.com')
            response = session.get(
                f'https://economy.roblox.com/v2/assets/{asset_id}/details',
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                return {
                    'product_id': data.get('ProductId') or data.get('Id'),
                    'seller_id': data.get('Creator', {}).get('Id') or data.get('Creator', {}).get('CreatorTargetId'),
                    'price': data.get('PriceInRobux', 0)
                }
            return None
        except Exception:
            return None
    
    def purchase_decal(self, session, product_id, seller_id, price, csrf_token, cookie):
        try:
            session.cookies.set('.ROBLOSECURITY', cookie, domain='.roblox.com')
            session.headers.update({'x-csrf-token': csrf_token})
            payload = {
                'expectedCurrency': 1,
                'expectedPrice': price,
                'expectedSellerId': seller_id
            }
            response = session.post(
                f'https://economy.roblox.com/v1/purchases/products/{product_id}',
                json=payload,
                timeout=10
            )
            response_data = response.json() if response.text else {}
            return response.status_code, response_data
        except Exception as e:
            return None, str(e)


def worker_thread(worker_id: int, cookie_queue: Queue, asset_id: str, tracker: PerformanceTracker, 
                  proxy_pool: list, running: list):
    client = DecalClient()
    proxy_index = worker_id % len(proxy_pool) if proxy_pool else 0
    
    while running[0]:
        try:
            cookie = cookie_queue.get_nowait()
        except Empty:
            break
        
        proxy = proxy_pool[proxy_index] if proxy_pool else None
        session = client.create_session(proxy)
        
        try:
            request_start = time.time()
            
            csrf_token = client.get_csrf_token(session, cookie)
            if not csrf_token:
                tracker.increment_failure()
                session.close()
                proxy_index = (proxy_index + 1) % len(proxy_pool) if proxy_pool else 0
                time.sleep(uniform(0.2, 0.5))
                continue

            product_info = client.get_product_info(session, asset_id, cookie)
            if not product_info:
                tracker.increment_failure()
                session.close()
                time.sleep(uniform(0.2, 0.5))
                continue

            status_code, response = client.purchase_decal(
                session,
                product_info['product_id'],
                product_info['seller_id'],
                product_info['price'],
                csrf_token,
                cookie
            )
            
            session.close()
            request_time = round(time.time() - request_start, 2)
            
            if status_code == 200:
                tracker.increment_success()
                completed, failed, rate = tracker.get_stats()
                print(format_output("Purchased", asset_id, request_time, completed, rate, "success"))
            elif status_code == 429:
                tracker.increment_failure()
                completed, failed, rate = tracker.get_stats()
                print(f"{Fore.YELLOW}Rate Limited{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}|{Style.RESET_ALL} Retrying... {Fore.LIGHTBLACK_EX}|{Style.RESET_ALL} Failed: {Fore.MAGENTA}{failed}{Style.RESET_ALL}")
                cookie_queue.put(cookie)
                time.sleep(3)
                proxy_index = (proxy_index + 1) % len(proxy_pool) if proxy_pool else 0
                continue
            elif status_code == 400:
                error_msg = str(response)
                if 'already' in error_msg.lower() or 'owned' in error_msg.lower():
                    tracker.increment_success()
                    completed, failed, rate = tracker.get_stats()
                    print(format_output("Purchase", asset_id, request_time, completed, rate, "already"))
                else:
                    tracker.increment_failure()
                    completed, failed, rate = tracker.get_stats()
                    print(format_output("Purchase", asset_id, request_time, completed, rate, "failed"))
            else:
                tracker.increment_failure()
                completed, failed, rate = tracker.get_stats()
                print(format_output("Purchase", asset_id, request_time, completed, rate, "failed"))
            
            proxy_index = (proxy_index + 1) % len(proxy_pool) if proxy_pool else 0
            time.sleep(uniform(0.2, 0.5))
            
        except Exception as e:
            tracker.increment_failure()
            time.sleep(uniform(0.5, 1.5))
        finally:
            cookie_queue.task_done()


def main():
    proxy_pool, cookie_pool = load_resources()
    
    if not cookie_pool:
        print(f"{Fore.RED}No cookies found in data/cookies.txt{Style.RESET_ALL}")
        return
    
    if not proxy_pool:
        print(f"{Fore.RED}No proxies found in data/proxies.txt{Style.RESET_ALL}")
        return
    
    try:
        thread_count = int(input(f"{Fore.CYAN}Threads: {Style.RESET_ALL}"))
        asset_id = input(f"{Fore.CYAN}Decal Asset ID: {Style.RESET_ALL}")
        
        if thread_count < 1:
            print(f"{Fore.RED}Threads must be at least 1{Style.RESET_ALL}")
            return
        if not asset_id.isdigit():
            print(f"{Fore.RED}Invalid asset ID{Style.RESET_ALL}")
            return
    except (ValueError, KeyboardInterrupt):
        return
        
    cookie_queue = Queue()
    for cookie in cookie_pool:
        cookie_queue.put(cookie)
    
    tracker = PerformanceTracker()
    running = [True]
    worker_threads = []
    
    for i in range(thread_count):
        thread = Thread(
            target=worker_thread,
            args=(i, cookie_queue, asset_id, tracker, proxy_pool, running),
            daemon=True
        )
        worker_threads.append(thread)
        thread.start()
        time.sleep(uniform(0.05, 0.15))
    
    try:
        cookie_queue.join()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Stopping...{Style.RESET_ALL}")
        running[0] = False
    
    for thread in worker_threads:
        thread.join(timeout=5)
    
    final_completed, final_failed, final_rate = tracker.get_stats()
    total_attempts = final_completed + final_failed
    success_rate = (final_completed / total_attempts * 100) if total_attempts > 0 else 0
    
    print(f"\n{Fore.CYAN}{'═' * 63}")
    print(f"{Fore.GREEN}Success: {Fore.MAGENTA}{final_completed}{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}|{Style.RESET_ALL} "
          f"{Fore.RED}Failed: {Fore.MAGENTA}{final_failed}{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}|{Style.RESET_ALL} "
          f"{Fore.CYAN}Rate: {Fore.MAGENTA}{success_rate:.1f}%{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}|{Style.RESET_ALL} "
          f"{Fore.MAGENTA}{final_rate}{Style.RESET_ALL}/min")
    print(f"{Fore.CYAN}{'═' * 63}{Style.RESET_ALL}")