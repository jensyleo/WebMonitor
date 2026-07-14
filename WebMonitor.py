"""
WebMonitor - Simple HTTP/HTTPS availability monitor

Copyright (C) 2026 jensyleo

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

Features:
- Monitors one or more URLs with retries and short timeouts.
- Normalizes schemeless URLs by trying HTTPS first, then HTTP.
- Distinguishes common errors: HTTP 1xx/2xx/3xx/4xx/5xx, DNS, SSL/TLS, timeout and connection.
- Explicitly identifies domains with no DNS resolution when no service is detectable.
- Shows colored messages and retries before reporting a definitive failure.
- Shows redirects (full 3xx chain) in blue and shows the final HTTP code of the destination.
- Optimized: suppresses the "OK 200" message when redirects were already reported, to avoid duplication.

Quick start:
- Dependencies: pip install requests colorama
- Run the script: python3 WebMonitor.py
- URL file (option 2): place a urls.txt file in the same directory as the script.

Note:
If you run it as a package module (requires Python package structure):
  cd /path/to/project/directory
  python -m EH.WebMonitor.WebMonitor

Messages:
- OK 2xx: "[+] {url} is online (Status: {code})" (suppressed if redirects were already reported)
- 1xx: "ℹ️ Site up with informational HTTP response {code}: {url}"
- 3xx: "🔁 Site up with HTTP redirect {chain of codes}: {url} → final URL"
- 4xx: "⚠️ Site up with client HTTP response {code}: {url}"
- 5xx: "⚠️ Site up with server HTTP error {code}: {url}"
- DNS: "🌐 DNS error at {url}: domain does not resolve"
- SSL/TLS: "🔒 SSL error at {url}: ..."
- Timeout: "⏳ Timeout at {url}: web service is not responding"
- Service unavailable (DNS resolves but no HTTP/HTTPS): "🚫 Web service unavailable: {url}"
- Too many redirects: "🔁 Too many redirects: {url}" (reported immediately, no retries)

Technical details:
- DNS pre-check: if the domain does not resolve, it is classified as a DNS error without attempting HTTP.
- Normalization with HEAD: tries HEAD on https:// first, and on failure falls back to http://, 1.0s timeout each.
- Main request: GET with a 2.0s timeout and allow_redirects=True; if redirects occur, they are reported along with the final code.
- Redirect detection: checks `response.history` to show the full chain of 3xx codes.
- Smart suppression: if redirects end in 2xx, only the chain is shown (no duplicate "OK 200").
- Retries: 2 attempts before reporting a definitive failure (total time ~4s for unavailable sites).
- TooManyRedirects exception: caught specifically and reported immediately without retries.
- urls.txt: empty lines and comments starting with '#' are ignored.
- Colors: green (OK 2xx), blue (1xx, 3xx, redirects and service unavailable), orange (4xx/5xx), red (errors and timeouts).
"""

__version__ = "1.0.1"

import socket
from urllib.parse import urlparse
import os
import sys
import time
from datetime import datetime
import signal
import shutil

try:
    import requests
    from colorama import Fore, init
except ImportError:
    print("Error: Missing dependencies.\nPlease run:\npip install requests colorama")
    sys.exit(1)

# Configure a requests session for better performance
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (compatible; WebMonitor/1.0)',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
})

# Custom exception used to interrupt monitoring
class MonitoringInterrupted(Exception):
    pass

# Initialize colorama
init(autoreset=True)

# Standard colorama colors used globally
RGB_GREEN = Fore.GREEN            # Green for the frame
RGB_SUCCESS = Fore.GREEN          # Green specifically for success messages
RGB_BLUE = Fore.CYAN              # Blue elements
RGB_YELLOW = Fore.YELLOW          # Yellow elements
RGB_RED = Fore.RED                # Errors
RGB_ORANGE = Fore.LIGHTRED_EX     # 4xx/5xx and SSL protocol errors
RGB_ASCII_GREEN = Fore.LIGHTGREEN_EX  # ASCII art
RESET_COLOR = Fore.RESET

# Unified messages for WebMonitor (single dictionary)
MESSAGES = {
    "TIMEOUT_FINAL": "⏳ Timeout at {url}: web service is not responding",
    "RETRY": "↻ Connection issue, retrying attempt {attempt}/{max_attempts} for {url}...",
    "CONN_ERROR_FINAL": "❌ Connection error with the web service: {url} ({detail})",
    "UNCLASSIFIED_FINAL": "⚠️ Unclassified error while querying the web service: {url} ({detail})",
    "HTTP_INFO": "ℹ️ Site up with informational HTTP response {code}: {url}",
    "HTTP_REDIRECT": "🔁 Site up with HTTP redirect {code}: {url}",
    "HTTP_REDIRECT_FINAL": "🔁 Site up with HTTP redirect {code}: {url} (will not be checked further to avoid infinite loops)",
    "HTTP_CLIENT": "⚠️ Site up with client HTTP response {code}: {url}",
    "HTTP_SERVER": "⚠️ Site up with server HTTP error {code}: {url}",
    "SSL_PROTOCOL": "🔒 SSL error at {url}: TLS protocol issue",
    "SSL_CERT": "🔒 SSL error at {url}: certificate issue",
    "DNS": "🌐 DNS error at {url}: domain does not resolve",
    "SERVICE_UNAVAILABLE": "🚫 Web service unavailable: {url}",
    "CONNECTION_REFUSED": "🔌 Connection error: website is not set up (closed port): {url}",
    "NO_ROUTE": "🌐 Network error: no route to host: {url}",
    "HTTP_NON_STANDARD": "{url} responded with a non-standard status: {code}",
    "TOO_MANY_REDIRECTS": "🔁 Too many redirects: {url}",
}

def get_terminal_width():
    """Get the terminal width"""
    try:
        return shutil.get_terminal_size().columns
    except (OSError, ValueError, AttributeError):
        return 80  # Default width if it cannot be obtained

def clear_screen():
    """Clears the screen in a cross-platform way."""
    os.system('cls' if os.name == 'nt' else 'clear')

def timestamp():
    """Returns the current time formatted for log messages."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def extract_host(url):
    """
    Extracts the hostname from a URL (with or without scheme).

    Args:
        url: URL to extract the hostname from

    Returns:
        str: Extracted hostname, or None on error
    """
    url_clean = url.strip()
    if url_clean.startswith(('http://', 'https://')):
        try:
            parsed = urlparse(url_clean)
            return parsed.hostname
        except (ValueError, AttributeError):
            return None
    else:
        # host[:port]/path style input (extract only the host before '/' and ':')
        return url_clean.split('/')[0].split(':')[0] if url_clean else None

def check_dns(host):
    """
    Checks whether a hostname resolves via DNS.

    Args:
        host: Hostname to check

    Returns:
        bool: True if the hostname resolves, False otherwise
    """
    if not host:
        return False
    try:
        socket.gethostbyname(host)
        return True
    except socket.gaierror:
        # Hostname does not exist or has no DNS records
        return False

def normalize_url(url, host=None):
    """
    Normalizes the URL by adding a protocol if none is present.

    Process:
    1. Checks DNS before attempting a connection (optimization)
    2. If there is no scheme, tries HTTPS first (1.0s timeout)
    3. If HTTPS fails, tries HTTP (1.0s timeout)
    4. Returns None if DNS fails or both protocols fail

    Args:
        url: URL to normalize (with or without scheme)
        host: Pre-extracted hostname, to avoid re-parsing it when the
              caller already has it (avoids a redundant DNS lookup)

    Returns:
        str: Normalized URL with scheme, or None on failure
    """
    url = url.strip()
    # DNS pre-check: avoids HTTP/HTTPS attempts if the domain doesn't exist
    if host is None:
        host = extract_host(url)
    if host and not check_dns(host):
        return None
    # If there is no scheme, automatically determine HTTPS or HTTP
    if not url.startswith(('http://', 'https://')):
        # Try HTTPS first (more secure and common protocol)
        try:
            response = session.head(f"https://{url}", timeout=1.0)
            return f"https://{url}"
        except requests.exceptions.RequestException:
            # If HTTPS fails, try HTTP (fallback)
            try:
                response = session.head(f"http://{url}", timeout=1.0)
                return f"http://{url}"
            except requests.exceptions.RequestException:
                # If both protocols fail, no web service is available
                return None
    return url

def monitor_website(url):
    """
    Monitors the status of a web URL with automatic retries.

    Process:
    1. Normalizes the URL (detects scheme and DNS)
    2. Performs a GET request following redirects (allow_redirects=True)
    3. Detects redirect chain in response.history and shows 3xx codes
    4. Classifies the final HTTP code (1xx-5xx) and shows the appropriate message
    5. Suppresses the "OK 200" message if a redirect chain was already shown (avoids duplication)
    6. Automatically retries on timeout or connection error (2 attempts max)

    Special exceptions:
    - TooManyRedirects: reported immediately without retries (retrying wouldn't help)
    - Timeout/ConnectionError: retried up to max_attempts

    Args:
        url: URL to monitor

    Returns:
        bool: True if the site is available (2xx), False otherwise
    """
    max_attempts = 2  # Number of attempts before reporting a definitive failure
    attempts = 0

    # Resolve the host and check DNS once per call, instead of on every retry
    host = extract_host(url)
    dns_error = bool(host) and not check_dns(host)

    while attempts < max_attempts:
        try:
            normalized_url = None if dns_error else normalize_url(url, host=host)
            if not normalized_url:
                attempts += 1
                if attempts == max_attempts:
                    if dns_error:
                        print(f"{RGB_RED}[{timestamp()}] [-] {MESSAGES['DNS'].format(url=url)}")
                    else:
                        print(f"{RGB_BLUE}[{timestamp()}] [-] {MESSAGES['SERVICE_UNAVAILABLE'].format(url=url)}")
                    return False
                else:
                    print(f"{RGB_YELLOW}[{timestamp()}] [*] {MESSAGES['RETRY'].format(attempt=attempts, max_attempts=max_attempts, url=url)}")
                    continue
            # Main request with a 2.0s timeout and automatic redirect following
            response = session.get(normalized_url, timeout=2.0, allow_redirects=True)

            # Detect and show the redirect chain if present in history
            # response.history contains all intermediate responses (3xx) before reaching the final destination
            has_history_redirects = False
            if response.history:  # response.history always exists, but may be empty
                # Build the redirect code chain (e.g. "301 -> 302 -> 307")
                chain_codes = " -> ".join(str(r.status_code) for r in response.history)
                print(f"{RGB_BLUE}[{timestamp()}] [-] {MESSAGES['HTTP_REDIRECT'].format(code=chain_codes, url=normalized_url)} → {response.url}")
                has_history_redirects = True

            # Check the final HTTP code (after processing all redirects)
            # Use response.url (final URL) if there were redirects, otherwise use normalized_url (original)
            final_url = response.url if has_history_redirects else normalized_url
            if response.status_code >= 100 and response.status_code < 200:
                print(f"{RGB_BLUE}[{timestamp()}] [-] {MESSAGES['HTTP_INFO'].format(code=response.status_code, url=final_url)}")
                return False
            elif response.status_code >= 200 and response.status_code < 300:
                # If there were redirects, the chain was already shown; don't duplicate with "OK 200"
                if not has_history_redirects:
                    print(f"{RGB_SUCCESS}[{timestamp()}] [+] {final_url} is online (Status: {response.status_code})")
                return True
            elif response.status_code >= 300 and response.status_code < 400:  # 3xx redirects
                if has_history_redirects:
                    # If history already contained redirects, indicate it won't be checked further to avoid loops
                    print(f"{RGB_BLUE}[{timestamp()}] [-] {MESSAGES['HTTP_REDIRECT_FINAL'].format(code=response.status_code, url=response.url)}")
                else:
                    # Direct redirect with no history
                    print(f"{RGB_BLUE}[{timestamp()}] [-] {MESSAGES['HTTP_REDIRECT'].format(code=response.status_code, url=normalized_url)}")
                return False  # Continue with the next URL
            elif response.status_code >= 400 and response.status_code < 500:  # 4xx client responses
                print(f"{RGB_ORANGE}[{timestamp()}] [-] {MESSAGES['HTTP_CLIENT'].format(code=response.status_code, url=final_url)}")
                return False  # Continue with the next URL
            elif response.status_code >= 500:  # 5xx server errors
                print(f"{RGB_ORANGE}[{timestamp()}] [-] {MESSAGES['HTTP_SERVER'].format(code=response.status_code, url=final_url)}")
                return False  # Continue with the next URL
            else:
                # Codes outside the standard range (100-599)
                print(f"{RGB_RED}[{timestamp()}] [-] {MESSAGES['HTTP_NON_STANDARD'].format(url=normalized_url, code=response.status_code)}")
                return False  # Continue with the next URL
        except requests.exceptions.Timeout:
            attempts += 1
            if attempts == max_attempts:
                print(f"{RGB_RED}[{timestamp()}] [-] {MESSAGES['TIMEOUT_FINAL'].format(url=url)}")
                return False
            else:
                print(f"{RGB_YELLOW}[{timestamp()}] [*] {MESSAGES['RETRY'].format(attempt=attempts, max_attempts=max_attempts, url=url)}")
        except requests.exceptions.ConnectionError as e:
            attempts += 1
            if attempts == max_attempts:
                # Distinguish between DNS errors and other connection errors
                error_msg = str(e).lower()
                if "tlsv1_alert_protocol_version" in error_msg or "protocol version" in error_msg:
                    print(f"{RGB_ORANGE}[{timestamp()}] [-] {MESSAGES['SSL_PROTOCOL'].format(url=url)}")
                elif "name or service not known" in error_msg or "nodename nor servname provided" in error_msg:
                    print(f"{RGB_RED}[{timestamp()}] [-] {MESSAGES['DNS'].format(url=url)}")
                elif "connection refused" in error_msg:
                    print(f"{RGB_RED}[{timestamp()}] [-] {MESSAGES['CONNECTION_REFUSED'].format(url=url)}")
                elif "no route to host" in error_msg:
                    print(f"{RGB_RED}[{timestamp()}] [-] {MESSAGES['NO_ROUTE'].format(url=url)}")
                else:
                    print(f"{RGB_RED}[{timestamp()}] [-] {MESSAGES['CONN_ERROR_FINAL'].format(url=url, detail=str(e))}")
                return False
            else:
                print(f"{RGB_YELLOW}[{timestamp()}] [*] {MESSAGES['RETRY'].format(attempt=attempts, max_attempts=max_attempts, url=url)}")
        except requests.exceptions.TooManyRedirects:
            # Too many redirects: retrying wouldn't help, return immediately
            print(f"{RGB_BLUE}[{timestamp()}] [-] {MESSAGES['TOO_MANY_REDIRECTS'].format(url=url)}")
            return False  # Continue with the next URL
        except requests.exceptions.RequestException as e:
            attempts += 1
            if attempts == max_attempts:
                # Distinguish other error types
                error_msg = str(e).lower()
                if "ssl" in error_msg or "certificate" in error_msg:
                    print(f"{RGB_RED}[{timestamp()}] [-] {MESSAGES['SSL_CERT'].format(url=url)}")
                else:
                    print(f"{RGB_RED}[{timestamp()}] [-] {MESSAGES['UNCLASSIFIED_FINAL'].format(url=url, detail=str(e))}")
                return False  # Continue with the next URL
            else:
                print(f"{RGB_YELLOW}[{timestamp()}] [*] {MESSAGES['RETRY'].format(attempt=attempts, max_attempts=max_attempts, url=url)}")

    return False

def signal_handler(signum, frame):
    """Signal handler for CTRL+C"""
    print(f"\n{RGB_BLUE}[*] Monitoring stopped by the user.")
    print(f"{RGB_YELLOW}{'═'*54}")
    # Raise an exception to interrupt monitoring
    raise MonitoringInterrupted()

def continuous_monitoring(urls):
    """
    Continuously monitors the URLs until CTRL+C is pressed.

    Args:
        urls: A single URL (str) or a list of URLs (list) to monitor

    The loop continues until the user presses CTRL+C, which raises
    MonitoringInterrupted and stops monitoring cleanly.
    """
    # Configure the signal handler for CTRL+C
    signal.signal(signal.SIGINT, signal_handler)

    print(f"\n{RGB_YELLOW}Monitoring... Press CTRL+C to stop.")

    try:
        while True:
            if isinstance(urls, list):
                for url in urls:
                    monitor_website(url)
            else:
                monitor_website(urls)

            time.sleep(1)  # Wait 1 second between each full cycle
    except MonitoringInterrupted:
        # Monitoring was interrupted by CTRL+C - exit cleanly
        pass

def read_urls(file_path):
    """
    Reads URLs from a text file, filtering out empty lines and comments.

    Args:
        file_path: Path to the file containing the URLs (one per line)

    Returns:
        list: List of clean URLs, or an empty list on error
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            lines = file.read().splitlines()
            # Filter out empty lines, whitespace and comments starting with '#'
            urls = []
            for line in lines:
                cleaned = line.strip()
                if not cleaned:  # Empty line
                    continue
                if cleaned.startswith('#'):  # Comment
                    continue
                urls.append(cleaned)
            return urls
    except FileNotFoundError:
        print(f"\n{RGB_RED}[!] Error: urls.txt file not found")
        return []
    except PermissionError:
        print(f"\n{RGB_RED}[!] Error: you don't have permission to read urls.txt")
        return []
    except IsADirectoryError:
        print(f"\n{RGB_RED}[!] Error: urls.txt is a directory, not a file")
        return []
    except UnicodeDecodeError as e:
        print(f"\n{RGB_RED}[!] Error: encoding issue while reading urls.txt")
        print(f"{RGB_YELLOW}Detail: {str(e)}")
        return []
    except (IOError, OSError) as e:
        print(f"\n{RGB_RED}[!] I/O error while reading urls.txt")
        print(f"{RGB_YELLOW}Detail: {str(e)}")
        return []

def main():
    while True:  # Main loop to return to the menu
        # Banner with dynamically centered ASCII art
        terminal_width = get_terminal_width()
        menu_width = 52
        margin = (terminal_width - menu_width) // 2

        ascii_art = [
            r"██╗    ██╗███████╗██████╗ ███╗   ███╗ ██████╗ ███╗   ██╗██╗████████╗ ██████╗ ██████╗ ",
            r"██║    ██║██╔════╝██╔══██╗████╗ ████║██╔═══██╗████╗  ██║██║╚══██╔══╝██╔═══██╗██╔══██╗",
            r"██║ █╗ ██║█████╗  ██████╔╝██╔████╔██║██║   ██║██╔██╗ ██║██║   ██║   ██║   ██║██████╔╝",
            r"██║███╗██║██╔══╝  ██╔══██╗██║╚██╔╝██║██║   ██║██║╚██╗██║██║   ██║   ██║   ██║██╔══██╗",
            r"╚███╔███╔╝███████╗██████╔╝██║ ╚═╝ ██║╚██████╔╝██║ ╚████║██║   ██║   ╚██████╔╝██║  ██║",
            r" ╚══╝╚══╝ ╚══════╝╚═════╝ ╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝",
        ]
        ascii_margin = max((terminal_width - max(len(line) for line in ascii_art)) // 2, 0)

        print()
        for line in ascii_art:
            print(f"{RGB_ASCII_GREEN}{' ' * ascii_margin}{line}{RESET_COLOR}")

        # Dynamically centered menu options
        print(f"\n{RGB_GREEN}{' ' * margin}╔{'═' * menu_width}╗{RESET_COLOR}")
        print(f"{RGB_GREEN}{' ' * margin}║{RGB_BLUE}{'WEB MONITOR':^52}{RGB_GREEN}║{RESET_COLOR}")
        print(f"{RGB_GREEN}{' ' * margin}║{Fore.WHITE}{'Version 1.0.1':^52}{RGB_GREEN}║{RESET_COLOR}")
        print(f"{RGB_GREEN}{' ' * margin}╠{'═' * menu_width}╣{RESET_COLOR}")
        print(f"{RGB_GREEN}{' ' * margin}║ {RGB_YELLOW}[1]{RGB_BLUE} ⚡ {Fore.WHITE}Monitor a URL{' ' * 31}{RGB_GREEN}║{RESET_COLOR}")
        print(f"{RGB_GREEN}{' ' * margin}║ {RGB_YELLOW}[2]{RGB_BLUE} 📋 {Fore.WHITE}Monitor URLs from a file{' ' * 20}{RGB_GREEN}║{RESET_COLOR}")
        print(f"{RGB_GREEN}{' ' * margin}║ {RGB_YELLOW}[Q]{RGB_BLUE} ❌ {Fore.WHITE}Exit{' ' * 40}{RGB_GREEN}║{RESET_COLOR}")
        print(f"{RGB_GREEN}{' ' * margin}╚{'═' * menu_width}╝{RESET_COLOR}")

        option = input(f"\n{RGB_BLUE}[?] {Fore.WHITE}Select an option {RGB_YELLOW}(1-2 or Q){Fore.WHITE}: ")

        if option == "1":
            url = input(f"\n{RGB_BLUE}[?] {Fore.WHITE}Enter the URL to monitor: ")
            print(f"\n{RGB_YELLOW}{'═' * 54}")
            continuous_monitoring(url)
            input(f"\n{RGB_BLUE}[*] {Fore.WHITE}Press ENTER to return to the main menu...")
            clear_screen()

        elif option == "2":
            # Look for the 'urls.txt' file in the same directory where the script runs
            file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'urls.txt')
            print(f"\n{RGB_BLUE}[*] {Fore.WHITE}Looking for the urls.txt file...")
            print(f"\n{RGB_YELLOW}{'═' * 54}")

            urls = read_urls(file_path)
            if urls:
                print(f"\n{RGB_BLUE}[*] {Fore.WHITE}Found {RGB_YELLOW}{len(urls)}{Fore.WHITE} URLs to monitor")
                print(f"{RGB_YELLOW}{'═' * 54}")
                continuous_monitoring(urls)
                input(f"\n{RGB_BLUE}[*] {Fore.WHITE}Press ENTER to return to the main menu...")
                clear_screen()
            else:
                input(f"\n{RGB_BLUE}[*] {Fore.WHITE}Press ENTER to return to the main menu...")
                clear_screen()

        elif option.upper() == "Q":
            print(f"\n{RGB_BLUE}[*] {Fore.WHITE}Thanks for using Web Monitor")
            print(f"{RGB_YELLOW}{'═' * 54}")
            sys.exit(0)

        else:
            print(f"\n{RGB_RED}[!] Invalid option. Please select 1-2 or Q.")
            print(f"{RGB_YELLOW}{'═' * 54}")
            input(f"\n{RGB_BLUE}[*] {Fore.WHITE}Press ENTER to continue...")
            clear_screen()

if __name__ == "__main__":
    main()
