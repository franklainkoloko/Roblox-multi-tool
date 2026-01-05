import os
import sys
from colorama import Fore, Style, init

init(autoreset=True)

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_banner():
    banner = f"""
{Fore.CYAN}
                                                              
                     {Fore.WHITE}Need help? Contact @kupk on Discord.{Fore.CYAN}       
               
"""
    print(banner)

def print_menu():
    print(f"  {Fore.MAGENTA}[1]{Style.RESET_ALL} {Fore.WHITE}Join Groups{Style.RESET_ALL}")
    print(f"  {Fore.MAGENTA}[2]{Style.RESET_ALL} {Fore.WHITE}Favorite Assets{Style.RESET_ALL}")
    print(f"  {Fore.MAGENTA}[3]{Style.RESET_ALL} {Fore.WHITE}Purchase Decals{Style.RESET_ALL}")
    print(f"  {Fore.MAGENTA}[4]{Style.RESET_ALL} {Fore.WHITE}Send Friend Requests{Style.RESET_ALL}")
    print(f"  {Fore.MAGENTA}[0]{Style.RESET_ALL} {Fore.RED}Exit{Style.RESET_ALL}")
    print()

def main():
    while True:
        clear_screen()
        print_banner()
        print_menu()
        
        try:
            choice = input(f"{Fore.CYAN}Select: {Style.RESET_ALL}").strip()      
            
            if choice == "1":
                from src.group_joiner import main as group_main
                clear_screen()
                group_main()
                input(f"\n{Fore.CYAN}Press Enter to return to menu...{Style.RESET_ALL}")
            
            elif choice == "2":
                from src.favorite_assets import main as favorite_main
                clear_screen()
                favorite_main()
                input(f"\n{Fore.CYAN}Press Enter to return to menu...{Style.RESET_ALL}")
            
            elif choice == "3":
                from src.decal_botter import main as decal_main
                clear_screen()
                decal_main()
                input(f"\n{Fore.CYAN}Press Enter to return to menu...{Style.RESET_ALL}")
            
            elif choice == "4":
                from src.friend_request import main as friend_main
                clear_screen()
                friend_main()
                input(f"\n{Fore.CYAN}Press Enter to return to menu...{Style.RESET_ALL}")
            
            
            elif choice == "0":
                clear_screen()
                print(f"\n{Fore.CYAN}Thanks for using Roblox Automation Suite!{Style.RESET_ALL}\n")
                sys.exit(0)
            
            else:
                print(f"\n{Fore.RED}Invalid choice. Please try again.{Style.RESET_ALL}")
                input(f"{Fore.CYAN}Press Enter to continue...{Style.RESET_ALL}")
        
        except KeyboardInterrupt:
            clear_screen()
            sys.exit(0)
        except Exception as e:
            print(f"\n{Fore.RED}Error: {str(e)}{Style.RESET_ALL}")
            input(f"{Fore.CYAN}Press Enter to continue...{Style.RESET_ALL}")

if __name__ == "__main__":
    main()