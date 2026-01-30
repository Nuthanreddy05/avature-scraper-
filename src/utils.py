"""
Utility functions and helpers for the Avature scraper.

Provides logging setup, file I/O, URL handling, rate limiting,
and common helper functions used across all modules.
"""

import json
import csv
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urljoin, urlparse
from functools import wraps

import colorlog


# ============================================================================
# PATH CONFIGURATION
# ============================================================================

def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent


def get_input_dir() -> Path:
    """Get the input directory path."""
    return get_project_root() / "input"


def get_output_dir() -> Path:
    """Get the output directory path."""
    output_dir = get_project_root() / "output"
    output_dir.mkdir(exist_ok=True)
    return output_dir


def get_logs_dir() -> Path:
    """Get the logs directory path."""
    logs_dir = get_project_root() / "logs"
    logs_dir.mkdir(exist_ok=True)
    return logs_dir


def get_cache_dir() -> Path:
    """Get the cache directory path."""
    cache_dir = get_project_root() / "cache"
    cache_dir.mkdir(exist_ok=True)
    return cache_dir


# ============================================================================
# LOGGING SETUP
# ============================================================================

def setup_logger(
    name: str,
    log_file: Optional[str] = None,
    level: int = logging.INFO,
    console: bool = True
) -> logging.Logger:
    """
    Set up a logger with colored console output and optional file output.
    
    Args:
        name: Logger name
        log_file: Optional log file name (saved to logs directory)
        level: Logging level
        console: Whether to output to console
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Clear existing handlers
    logger.handlers = []
    
    # Console handler with colors
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        
        color_formatter = colorlog.ColoredFormatter(
            '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S',
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            }
        )
        console_handler.setFormatter(color_formatter)
        logger.addHandler(console_handler)
    
    # File handler
    if log_file:
        log_path = get_logs_dir() / log_file
        file_handler = logging.FileHandler(log_path, encoding='utf-8')
        file_handler.setLevel(level)
        
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    return logger


# ============================================================================
# FILE I/O
# ============================================================================

def save_json(data: Any, filename: str, output_dir: Optional[Path] = None) -> Path:
    """
    Save data to a JSON file.
    
    Args:
        data: Data to save
        filename: Output filename
        output_dir: Optional output directory (defaults to output/)
        
    Returns:
        Path to saved file
    """
    output_dir = output_dir or get_output_dir()
    filepath = output_dir / filename
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    
    return filepath


def load_json(filename: str, input_dir: Optional[Path] = None) -> Any:
    """
    Load data from a JSON file.
    
    Args:
        filename: Input filename
        input_dir: Optional input directory
        
    Returns:
        Loaded data
    """
    input_dir = input_dir or get_input_dir()
    filepath = input_dir / filename
    
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_jsonl(data: List[Dict], filename: str, output_dir: Optional[Path] = None) -> Path:
    """
    Save data to a JSON Lines file.
    
    Args:
        data: List of dicts to save
        filename: Output filename
        output_dir: Optional output directory
        
    Returns:
        Path to saved file
    """
    output_dir = output_dir or get_output_dir()
    filepath = output_dir / filename
    
    with open(filepath, 'w', encoding='utf-8') as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False, default=str) + '\n')
    
    return filepath


def load_jsonl(filename: str, input_dir: Optional[Path] = None) -> List[Dict]:
    """
    Load data from a JSON Lines file.
    
    Args:
        filename: Input filename
        input_dir: Optional input directory
        
    Returns:
        List of loaded dicts
    """
    input_dir = input_dir or get_output_dir()
    filepath = input_dir / filename
    
    data = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    
    return data


def save_csv(data: List[Dict], filename: str, output_dir: Optional[Path] = None) -> Path:
    """
    Save data to a CSV file.
    
    Args:
        data: List of dicts to save
        filename: Output filename
        output_dir: Optional output directory
        
    Returns:
        Path to saved file
    """
    if not data:
        return None
    
    output_dir = output_dir or get_output_dir()
    filepath = output_dir / filename
    
    # Get all unique keys from all records
    all_keys = set()
    for item in data:
        all_keys.update(item.keys())
    
    # Sort keys for consistent column order
    fieldnames = sorted(all_keys)
    
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(data)
    
    return filepath


def save_urls(urls: List[str], filename: str, output_dir: Optional[Path] = None) -> Path:
    """
    Save URLs to a text file (one per line).
    
    Args:
        urls: List of URLs
        filename: Output filename
        output_dir: Optional output directory
        
    Returns:
        Path to saved file
    """
    output_dir = output_dir or get_input_dir()
    filepath = output_dir / filename
    
    with open(filepath, 'w', encoding='utf-8') as f:
        for url in urls:
            f.write(url + '\n')
    
    return filepath


def load_urls(filename: str, input_dir: Optional[Path] = None) -> List[str]:
    """
    Load URLs from a text file (one per line).
    
    Args:
        filename: Input filename
        input_dir: Optional input directory
        
    Returns:
        List of URLs
    """
    input_dir = input_dir or get_input_dir()
    filepath = input_dir / filename
    
    if not filepath.exists():
        return []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]


# ============================================================================
# URL UTILITIES
# ============================================================================

def normalize_url(url: str) -> str:
    """
    Normalize a URL for consistent comparison.
    
    Args:
        url: URL to normalize
        
    Returns:
        Normalized URL
    """
    url = url.strip().rstrip('/')
    
    # Ensure protocol
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    # Parse and reconstruct
    parsed = urlparse(url)
    
    # Normalize to lowercase domain
    normalized = f"{parsed.scheme}://{parsed.netloc.lower()}{parsed.path}"
    
    return normalized


def extract_domain(url: str) -> str:
    """
    Extract the domain from a URL.
    
    Args:
        url: URL to extract domain from
        
    Returns:
        Domain string
    """
    parsed = urlparse(url)
    return parsed.netloc.lower()


def extract_company_name(url: str) -> str:
    """
    Extract company name from Avature URL (both .avature.net and custom domains).
    
    Examples:
        https://bloomberg.avature.net/careers -> Bloomberg
        https://careers.twosigma.com/careers -> Two Sigma
        https://jobs.acme.com -> Acme
        https://jobs.auspost.com.au -> Auspost
    
    Args:
        url: Avature URL
        
    Returns:
        Company name (title case)
    """
    domain = extract_domain(url)
    
    # Skip share/social URLs (exact match only)
    skip_domains = ['wa.me', 't.co', 'bit.ly', 'ow.ly', 'tinyurl.com']
    if domain in skip_domains or any(domain.startswith(skip + '/') for skip in skip_domains):
        return 'Unknown'
    
    # Handle .avature.net domains
    if '.avature.net' in domain:
        company = domain.replace('.avature.net', '')
        
        # Handle subdomains like jobs.acme.avature.net
        parts = company.split('.')
        if len(parts) > 1:
            # Take the main company part (usually second-to-last)
            company = parts[-1] if parts[-1] != 'jobs' else parts[-2]
    else:
        # Handle custom domains like careers.twosigma.com, jobs.company.com
        parts = domain.split('.')
        
        # Remove common prefixes (careers, jobs, apply, etc.)
        prefixes_to_skip = ['careers', 'jobs', 'apply', 'recruiting', 'talent', 'www']
        
        # Handle country code TLDs (.com.au, .co.uk, etc.)
        country_codes = ['.com.au', '.co.uk', '.com.br', '.co.in', '.co.nz']
        has_country_code = any(domain.endswith(cc) for cc in country_codes)
        
        if len(parts) >= 2:
            # If first part is a common prefix
            if parts[0] in prefixes_to_skip:
                if has_country_code and len(parts) >= 4:
                    # jobs.auspost.com.au -> auspost
                    company = parts[-3]
                elif len(parts) >= 3:
                    # careers.twosigma.com -> twosigma
                    company = parts[-2]
                else:
                    company = parts[-2]
            else:
                # Handle domain directly
                if has_country_code and len(parts) >= 3:
                    # auspost.com.au -> auspost
                    company = parts[-3]
                else:
                    # twosigma.com -> twosigma or ea.com -> ea
                    company = parts[-2] if len(parts) > 2 else parts[0]
        else:
            company = parts[0]
    
    # Known company mappings for short domains
    company_mappings = {
        'ea': 'EA',
        'ge': 'GE', 
        'hp': 'HP',
        '3m': '3M',
    }
    
    company_lower = company.lower()
    if company_lower in company_mappings:
        return company_mappings[company_lower]
    
    # Convert to title case and clean
    company = company.replace('-', ' ').replace('_', ' ')
    company = ' '.join(word.capitalize() for word in company.split())
    
    return company


def make_absolute_url(base_url: str, relative_url: str) -> str:
    """
    Convert a relative URL to absolute.
    
    Args:
        base_url: Base URL
        relative_url: Relative URL to convert
        
    Returns:
        Absolute URL
    """
    return urljoin(base_url, relative_url)


def is_avature_url(url: str) -> bool:
    """
    Check if URL is an Avature-hosted site.
    
    Args:
        url: URL to check
        
    Returns:
        True if Avature URL
    """
    domain = extract_domain(url)
    return 'avature.net' in domain


def extract_job_id_from_url(url: str) -> Optional[str]:
    """
    Extract job ID from a job detail URL.
    
    Best practice: Try simplest method first (URL splitting), then regex.
    
    Handles Avature format: /JobDetail/Job-Title-Text/12345
    
    Patterns:
        /JobDetail/Job-Title/12345
        /job/12345
        /jobs/12345
        ?jobId=12345
    
    Args:
        url: Job URL
        
    Returns:
        Job ID string or None
    """
    # Method 1: String splitting (fastest - recommended by Stack Overflow)
    # Avature URLs end with: /JobDetail/Title-Text/12345
    parts = url.rstrip('/').split('/')
    if parts and parts[-1].isdigit() and len(parts[-1]) >= 4:
        return parts[-1]
    
    # Method 2: Regex for digits at end of URL path
    # Matches: /JobDetail/Title/12345 or /some-path/12345
    match = re.search(r'/(\d{4,})(?:[/?#]|$)', url)
    if match:
        return match.group(1)
    
    # Method 3: Query parameters
    patterns = [
        r'[?&]jobId=(\d+)',
        r'[?&]id=(\d+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return None


# ============================================================================
# RATE LIMITING & RETRY
# ============================================================================

class RateLimiter:
    """Simple rate limiter for API requests."""
    
    def __init__(self, requests_per_second: float = 2.0):
        """
        Initialize rate limiter.
        
        Args:
            requests_per_second: Maximum requests per second
        """
        self.min_interval = 1.0 / requests_per_second
        self.last_request_time = 0.0
    
    def wait(self):
        """Wait if necessary to respect rate limit."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_request_time = time.time()


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    Decorator for retrying a function with exponential backoff.
    
    Args:
        max_retries: Maximum number of retries
        initial_delay: Initial delay in seconds
        backoff_factor: Multiplier for delay after each retry
        exceptions: Tuple of exceptions to catch
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        time.sleep(delay)
                        delay *= backoff_factor
            
            raise last_exception
        
        return wrapper
    return decorator


# ============================================================================
# DATA UTILITIES
# ============================================================================

def clean_text(text: str) -> str:
    """
    Clean text by removing extra whitespace.
    
    Args:
        text: Text to clean
        
    Returns:
        Cleaned text
    """
    if not text:
        return ""
    
    # Replace multiple whitespace with single space
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


def truncate_text(text: str, max_length: int = 500, suffix: str = "...") -> str:
    """
    Truncate text to a maximum length.
    
    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add when truncated
        
    Returns:
        Truncated text
    """
    if not text or len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


def get_timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.utcnow().isoformat() + 'Z'


def format_duration(seconds: float) -> str:
    """
    Format duration in human-readable format.
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        Formatted string (e.g., "2h 15m 30s")
    """
    hours, remainder = divmod(int(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 or not parts:
        parts.append(f"{seconds}s")
    
    return " ".join(parts)


def chunk_list(lst: List, chunk_size: int) -> List[List]:
    """
    Split a list into chunks of specified size.
    
    Args:
        lst: List to split
        chunk_size: Size of each chunk
        
    Returns:
        List of chunks
    """
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


# ============================================================================
# CHECKPOINTING
# ============================================================================

class Checkpointer:
    """Handles saving and loading progress checkpoints."""
    
    def __init__(self, checkpoint_name: str, interval: int = 50):
        """
        Initialize checkpointer.
        
        Args:
            checkpoint_name: Base name for checkpoint files
            interval: Save checkpoint every N items
        """
        self.checkpoint_name = checkpoint_name
        self.interval = interval
        self.output_dir = get_output_dir()
        self.logger = setup_logger('checkpointer')
    
    def get_checkpoint_path(self, count: int) -> Path:
        """Get path for a checkpoint file."""
        return self.output_dir / f"checkpoint_{self.checkpoint_name}_{count}.jsonl"
    
    def save(self, data: List[Dict], count: int):
        """Save a checkpoint."""
        filepath = self.get_checkpoint_path(count)
        save_jsonl(data, filepath.name)
        self.logger.info(f"Checkpoint saved: {count} items to {filepath.name}")
    
    def should_save(self, count: int) -> bool:
        """Check if a checkpoint should be saved."""
        return count > 0 and count % self.interval == 0
    
    def load_latest(self) -> tuple:
        """
        Load the latest checkpoint.
        
        Returns:
            Tuple of (data, count) or ([], 0) if no checkpoint
        """
        checkpoint_files = list(self.output_dir.glob(f"checkpoint_{self.checkpoint_name}_*.jsonl"))
        
        if not checkpoint_files:
            return [], 0
        
        # Find latest by count
        latest = max(checkpoint_files, key=lambda p: int(p.stem.split('_')[-1]))
        count = int(latest.stem.split('_')[-1])
        
        data = load_jsonl(latest.name)
        self.logger.info(f"Loaded checkpoint: {count} items from {latest.name}")
        
        return data, count
    
    def clear(self):
        """Remove all checkpoints."""
        for checkpoint in self.output_dir.glob(f"checkpoint_{self.checkpoint_name}_*.jsonl"):
            checkpoint.unlink()
        self.logger.info("Cleared all checkpoints")


# ============================================================================
# HTTP SESSION
# ============================================================================

def get_default_headers() -> Dict[str, str]:
    """Get default HTTP headers that mimic a real browser."""
    return {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
    }


def get_api_headers() -> Dict[str, str]:
    """Get headers for API requests."""
    return {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Content-Type': 'application/json',
    }
