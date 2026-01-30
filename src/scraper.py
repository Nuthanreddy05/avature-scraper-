"""
Hybrid Web Scraper for Avature Sites.

Implements a three-tier cascading fallback approach:
1. HTTP + BeautifulSoup (fastest, 70% success)
2. API Detection (clean JSON data, 20% success)
3. Playwright-Stealth (JavaScript rendering, 10% success)

Target: 93%+ success rate across 1,000+ sites

Optimized based on pattern analysis of 881K URLs:
- Primary path: /jobs/SearchJobs/
- Pagination: jobOffset with increment of 10
- Common paths: /jobs, /en_US/jobs, /careers
"""

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    from playwright_stealth import Stealth
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Stealth = None

from .extractors import extract_job_data, extract_jobs_from_listing, extract_jsonld_data
from .cleaner import clean_description
from .deduplicator import deduplicate_jobs
from .validator import validate_jobs, clean_jobs_batch, calculate_batch_quality
from .api_scraper import AvatureAPIScaper  # NEW: API scraper
from .utils import (
    setup_logger,
    get_default_headers,
    get_api_headers,
    normalize_url,
    extract_domain,
    extract_company_name,
    save_json,
    save_jsonl,
    save_csv,
    load_urls,
    load_json,
    get_input_dir,
    get_output_dir,
    get_timestamp,
    format_duration,
    RateLimiter,
    Checkpointer,
    chunk_list,
)


logger = setup_logger('scraper', 'scraper.log')


# ============================================================================
# CONFIGURATION
# ============================================================================

class ScrapeMethod(Enum):
    """Scraping methods in order of preference."""
    HTTP = "http"
    API = "api"
    PLAYWRIGHT = "playwright"


@dataclass
class ScraperConfig:
    """Scraper configuration optimized from pattern analysis."""
    # Concurrency - REDUCED for better reliability
    max_workers: int = 5  # Reduced from 10 to avoid rate limiting
    requests_per_second: float = 1.0  # Reduced from 2.0
    
    # Timeouts (seconds) - INCREASED for Playwright
    http_timeout: int = 20  # Increased from 15
    api_timeout: int = 15  # Increased from 10
    playwright_timeout: int = 60000  # Increased from 30000 (60s)
    
    # Pagination - optimized from pattern analysis (98% use jobOffset by 10)
    max_pages_per_site: int = 100
    jobs_per_page: int = 10  # Most common from analysis
    pagination_param: str = 'jobOffset'  # 98% of sites use this
    
    # Test mode settings
    test_one_job_mode: bool = False
    test_date_threshold_days: int = 60  # Jobs older than this = stale
    
    # Paths to try in order (from pattern analysis)
    paths_to_try: List[str] = field(default_factory=lambda: [
        '/jobs/SearchJobs',      # Most common (125K occurrences)
        '/en_US/jobs/SearchJobs',
        '/jobs',
        '/en_US/jobs',
        '/careers/SearchJobs',
        '/careers',
    ])
    
    # Retries
    max_retries: int = 3  # Increased from 2
    retry_delay: float = 3.0  # Increased from 2.0
    
    # Checkpointing
    checkpoint_interval: int = 25  # Reduced from 50 for more frequent saves
    
    # Browser settings
    headless: bool = True
    
    # Quality thresholds
    min_jobs_per_site: int = 0  # 0 = accept all, trigger Playwright more
    
    # Output
    output_formats: List[str] = field(default_factory=lambda: ['json', 'csv', 'jsonl'])


@dataclass
class ScrapeResult:
    """Result of scraping a single site."""
    url: str
    success: bool
    method: Optional[ScrapeMethod] = None
    jobs: List[Dict] = field(default_factory=list)
    error: Optional[str] = None
    duration_seconds: float = 0.0
    pages_scraped: int = 0


# ============================================================================
# HTTP SCRAPER (Method 1)
# ============================================================================

class HttpScraper:
    """HTTP + BeautifulSoup scraper optimized for Avature sites."""
    
    def __init__(self, config: ScraperConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(get_default_headers())
        self.rate_limiter = RateLimiter(config.requests_per_second)
    
    def scrape_site(self, url: str) -> Optional[List[Dict]]:
        """
        Scrape all jobs from a site using HTTP requests.
        Tries multiple paths based on pattern analysis.
        
        Args:
            url: Site URL (domain or full URL)
            
        Returns:
            List of job dicts or None if failed
        """
        # Extract base domain
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        # Try each path in order
        for path in self.config.paths_to_try:
            try:
                test_url = f"{base_url}{path}"
                jobs = self._try_scrape_path(test_url, base_url)
                if jobs:
                    logger.debug(f"Success with path {path} for {base_url}")
                    return jobs
            except Exception as e:
                logger.debug(f"Path {path} failed for {base_url}: {e}")
                continue
        
        # Fallback: try the original URL as-is
        try:
            return self._try_scrape_path(url, base_url)
        except Exception:
            return None
    
    def _try_scrape_path(self, url: str, base_url: str) -> Optional[List[Dict]]:
        """Try to scrape jobs from a specific URL path."""
        self.rate_limiter.wait()
        
        response = self.session.get(url, timeout=self.config.http_timeout)
        
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, 'lxml')
        
        # Check if page has job listings
        jobs = extract_jobs_from_listing(soup, url)
        
        if not jobs:
            # Maybe it's a single job page?
            job_data = extract_job_data(soup, url)
            if job_data.get('title'):
                return [job_data]
            return None
        
        # Handle pagination using jobOffset (98% of sites)
        all_jobs = list(jobs)
        page_count = 1
        
        while page_count < self.config.max_pages_per_site:
            # Test mode: stop after first page
            if self.config.test_one_job_mode and page_count >= 1:
                logger.debug(f"Test mode: stopping after first page for {url}")
                break
            
            offset = page_count * self.config.jobs_per_page
            next_url = self._build_pagination_url(url, offset)
            
            self.rate_limiter.wait()
            
            try:
                response = self.session.get(next_url, timeout=self.config.http_timeout)
                if response.status_code != 200:
                    break
                
                soup = BeautifulSoup(response.text, 'lxml')
                page_jobs = extract_jobs_from_listing(soup, next_url)
                
                if not page_jobs:
                    break
                
                # Check for duplicates (we've reached the end)
                new_urls = {j.get('application_url') for j in page_jobs}
                existing_urls = {j.get('application_url') for j in all_jobs}
                if new_urls.issubset(existing_urls):
                    break
                
                all_jobs.extend(page_jobs)
                page_count += 1
                
                # Safety limit
                if len(all_jobs) > 2000:
                    logger.debug(f"Hit safety limit of 2000 jobs for {url}")
                    break
                
            except Exception:
                break
        
        # Fetch full details for each job
        detailed_jobs = self._fetch_job_details(all_jobs, base_url)
        
        return detailed_jobs if detailed_jobs else None
    
    def _build_pagination_url(self, base_url: str, offset: int) -> str:
        """Build pagination URL using jobOffset parameter."""
        import re
        
        if 'jobOffset=' in base_url:
            return re.sub(r'jobOffset=\d+', f'jobOffset={offset}', base_url)
        elif '?' in base_url:
            return f"{base_url}&jobOffset={offset}"
        else:
            return f"{base_url}?jobOffset={offset}"
    
    def _fetch_job_details(self, jobs: List[Dict], base_url: str) -> List[Dict]:
        """Fetch full details for each job with Playwright fallback."""
        detailed_jobs = []
        
        for job in jobs:
            url = job.get('application_url')
            if not url:
                detailed_jobs.append(job)
                continue
            
            # Make URL absolute if needed
            if not url.startswith('http'):
                url = urljoin(base_url, url)
            
            full_job = None
            
            # Try HTTP first
            try:
                self.rate_limiter.wait()
                response = self.session.get(url, timeout=self.config.http_timeout)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'lxml')
                    full_job = extract_job_data(soup, url)
                    
                    # Check if we got the essential fields (description)
                    if full_job.get('description') and len(full_job.get('description', '')) > 50:
                        # Success! Merge with listing data
                        for key, value in job.items():
                            if not full_job.get(key) and value:
                                full_job[key] = value
                        detailed_jobs.append(full_job)
                        continue
                    
            except Exception:
                pass
            
            # HTTP failed or incomplete - try Playwright fallback
            if PLAYWRIGHT_AVAILABLE and not full_job:
                try:
                    with sync_playwright() as p:
                        browser = p.chromium.launch(headless=self.config.headless)
                        context = browser.new_context()
                        page = context.new_page()
                        
                        page.goto(url, wait_until='networkidle', timeout=self.config.playwright_timeout)
                        html = page.content()
                        
                        browser.close()
                        
                        soup = BeautifulSoup(html, 'lxml')
                        full_job = extract_job_data(soup, url)
                        
                        # Merge with listing data
                        for key, value in job.items():
                            if not full_job.get(key) and value:
                                full_job[key] = value
                        
                        detailed_jobs.append(full_job)
                        continue
                        
                except Exception as e:
                    logger.debug(f"Playwright fallback failed for {url}: {e}")
            
            # Fallback: use partial data from listing
            detailed_jobs.append(job)
        
        return detailed_jobs


# ============================================================================
# API SCRAPER (Method 2)
# ============================================================================

class ApiScraper:
    """API endpoint detection and scraping."""
    
    def __init__(self, config: ScraperConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(get_api_headers())
    
    def scrape_site(self, url: str) -> Optional[List[Dict]]:
        """
        Attempt to scrape using hidden API endpoints.
        
        Args:
            url: Site URL
            
        Returns:
            List of job dicts or None if API not found
        """
        api_url = self._detect_api(url)
        
        if not api_url:
            return None
        
        try:
            all_jobs = []
            offset = 0
            
            while True:
                payload = {
                    'jobOffset': offset,
                    'jobRecordsPerPage': self.config.jobs_per_page,
                }
                
                response = self.session.post(
                    api_url,
                    json=payload,
                    timeout=self.config.api_timeout
                )
                
                if response.status_code != 200:
                    break
                
                data = response.json()
                
                # Extract jobs from various response formats
                jobs = self._extract_jobs_from_api(data, url)
                
                if not jobs:
                    break
                
                all_jobs.extend(jobs)
                offset += self.config.jobs_per_page
                
                # Check for end of results
                total = data.get('totalJobs', data.get('total', data.get('count', 0)))
                if offset >= total or len(all_jobs) >= total:
                    break
                
                if len(all_jobs) > 1000:  # Safety limit
                    break
            
            return all_jobs if all_jobs else None
            
        except Exception as e:
            logger.debug(f"API scrape error for {url}: {e}")
            return None
    
    def _detect_api(self, url: str) -> Optional[str]:
        """Detect API endpoint for a site."""
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        
        # Common Avature API patterns (ENHANCED with more endpoints)
        api_patterns = [
            # Avature standard endpoints (most common)
            f"{base}/SearchJobsData",
            f"{base}/services/jobssearchservlet",  # Bank of America, etc.
            f"{base}/api/SearchJobs",
            f"{base}/api/jobs",
            f"{base}/api/v1/jobs",
            f"{base}/api/v2/jobs",
            # With /careers prefix
            f"{base}/careers/SearchJobsData",
            f"{base}/careers/SearchJobs",
            f"{base}/careers/api/jobs",
            # With locale prefix
            f"{base}/en_US/careers/SearchJobsData",
            f"{base}/en_US/SearchJobsData",
            # Dynamic replacement
            url.replace('/careers', '/SearchJobsData'),
            url.replace('/careers', '/api/SearchJobs'),
        ]
        
        for api_url in api_patterns:
            try:
                # Try POST first (most common)
                response = self.session.post(
                    api_url,
                    json={'jobOffset': 0, 'jobRecordsPerPage': 10},
                    timeout=5
                )
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        if 'jobs' in data or 'results' in data or 'items' in data:
                            logger.debug(f"Found API at {api_url}")
                            return api_url
                    except json.JSONDecodeError:
                        pass
                
                # Try GET
                response = self.session.get(api_url, timeout=5)
                if response.status_code == 200:
                    try:
                        data = response.json()
                        if 'jobs' in data or 'results' in data or 'items' in data:
                            logger.debug(f"Found API at {api_url}")
                            return api_url
                    except json.JSONDecodeError:
                        pass
                        
            except Exception:
                continue
        
        return None
    
    def _extract_jobs_from_api(self, data: Dict, base_url: str) -> List[Dict]:
        """Extract jobs from API response."""
        jobs = []
        
        # Find jobs array in response
        job_list = data.get('jobs') or data.get('results') or data.get('items') or []
        
        if isinstance(job_list, list):
            for item in job_list:
                job = self._parse_api_job(item, base_url)
                if job:
                    jobs.append(job)
        
        return jobs
    
    def _parse_api_job(self, item: Dict, base_url: str) -> Optional[Dict]:
        """Parse a single job from API response."""
        if not isinstance(item, dict):
            return None
        
        # Map common API field names
        job = {
            'job_id': str(item.get('id') or item.get('jobId') or item.get('job_id', '')),
            'title': item.get('title') or item.get('jobTitle') or item.get('name', ''),
            'description': item.get('description') or item.get('jobDescription', ''),
            'description_html': item.get('descriptionHtml') or item.get('description_html', ''),
            'location': item.get('location') or item.get('city') or item.get('office', ''),
            'department': item.get('department') or item.get('category') or item.get('team', ''),
            'employment_type': item.get('employmentType') or item.get('type', ''),
            'remote_type': item.get('remoteType') or item.get('workType', ''),
            'date_posted': item.get('postedDate') or item.get('datePosted') or item.get('created', ''),
            'company_name': item.get('company') or extract_company_name(base_url),
            'date_scraped': get_timestamp(),
        }
        
        # Build application URL
        job_id = job['job_id']
        if job_id:
            job['application_url'] = urljoin(base_url, f"/JobDetail/{job_id}")
        else:
            job['application_url'] = item.get('url') or item.get('applyUrl', '')
        
        # Clean description
        if job['description_html'] and not job['description']:
            job['description'] = clean_description(job['description_html'])
        
        return job if job.get('title') else None


# ============================================================================
# PLAYWRIGHT SCRAPER (Method 3)
# ============================================================================

class PlaywrightScraper:
    """Full browser automation for JavaScript-heavy sites."""
    
    def __init__(self, config: ScraperConfig):
        self.config = config
        
        if not PLAYWRIGHT_AVAILABLE:
            logger.warning("Playwright not available - install with 'pip install playwright playwright-stealth'")
    
    def scrape_site(self, url: str) -> Optional[List[Dict]]:
        """
        Scrape using Playwright browser automation.
        
        Args:
            url: Site URL
            
        Returns:
            List of job dicts or None if failed
        """
        if not PLAYWRIGHT_AVAILABLE:
            return None
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.config.headless)
                
                # Use Stealth context manager for anti-detection
                stealth = Stealth() if Stealth else None
                
                if stealth:
                    with stealth.use_sync(browser) as context:
                        page = context.new_page()
                        return self._scrape_with_page(page, url)
                else:
                    context = browser.new_context(
                        viewport={'width': 1920, 'height': 1080},
                        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                    )
                    page = context.new_page()
                    result = self._scrape_with_page(page, url)
                    browser.close()
                    return result
                
        except Exception as e:
            logger.debug(f"Playwright error for {url}: {e}")
            return None
    
    def _scrape_with_page(self, page, url: str) -> Optional[List[Dict]]:
        """Helper to scrape with a Playwright page."""
        try:
            # Navigate to page
            page.goto(url, wait_until='networkidle', timeout=self.config.playwright_timeout)
            
            # Enhanced Avature detection via JavaScript object inspection
            # This catches sites that hide Avature in JS but not HTML
            try:
                has_avature = page.evaluate('''() => {
                    return !!(
                        window.avature || 
                        window.Avature || 
                        window.avatureConfig ||
                        window.AvatureCareerPortal
                    );
                }''')
                if has_avature:
                    logger.debug(f"Detected Avature via window.avature object for {url}")
            except Exception:
                pass  # Not critical if JS check fails
            
            # Wait for job elements
            try:
                page.wait_for_selector('[class*="job"], article, .job-card', timeout=10000)
            except PlaywrightTimeout:
                pass
            
            # Get HTML
            html = page.content()
            
            # Parse with BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')
            
            # Extract jobs from listing
            jobs = extract_jobs_from_listing(soup, url)
            
            if jobs:
                return list(jobs)
            
            # Maybe single job page
            job_data = extract_job_data(soup, url)
            if job_data.get('title'):
                return [job_data]
            
            return None
            
        except Exception as e:
            logger.debug(f"Playwright page error for {url}: {e}")
            return None


# ============================================================================
# HYBRID SCRAPER (Main Class)
# ============================================================================

class HybridScraper:
    """
    Production-grade hybrid scraper with cascading fallback.
    
    Tries methods in order:
    1. HTTP + BeautifulSoup (fastest)
    2. API Detection (cleanest data)
    3. Playwright (JavaScript rendering)
    """
    
    def __init__(self, config: Optional[ScraperConfig] = None):
        self.config = config or ScraperConfig()
        
        # Initialize scrapers
        self.http_scraper = HttpScraper(self.config)
        self.api_scraper = ApiScraper(self.config)
        self.playwright_scraper = PlaywrightScraper(self.config)
        
        # Stats tracking
        self.stats = {
            'http_success': 0,
            'api_success': 0,
            'playwright_success': 0,
            'total_failed': 0,
            'failure_reasons': {},
        }
    
    def scrape_site(self, url: str) -> ScrapeResult:
        """
        Scrape a single site using cascading fallback.
        
        Args:
            url: Site URL to scrape
            
        Returns:
            ScrapeResult with jobs or error
        """
        start_time = time.time()
        url = normalize_url(url)
        
        logger.info(f"🔍 Scraping {url}")
        
        # ==========================================
        # Method 1: API (NEW PRIORITY!) ⚡
        # Fastest + cleanest JSON data
        # ==========================================
        logger.info("  1️⃣  Trying API...")
        jobs = self.api_scraper.scrape_site(url)
        if jobs and len(jobs) > 0:
            self.stats['api_success'] += 1
            logger.info(f"  ✅ API Success: {len(jobs)} jobs in {time.time() - start_time:.1f}s")
            return ScrapeResult(
                url=url,
                success=True,
                method=ScrapeMethod.API,
                jobs=jobs,
                duration_seconds=time.time() - start_time
            )
        logger.info("  ❌ API not available")
        
        # ==========================================
        # Method 2: HTTP with Pagination
        # Fast but needs HTML cleaning
        # ==========================================
        logger.info("  2️⃣  Trying HTTP...")
        jobs = self.http_scraper.scrape_site(url)
        if jobs and len(jobs) > 0:
            self.stats['http_success'] += 1
            logger.info(f"  ✅ HTTP Success: {len(jobs)} jobs in {time.time() - start_time:.1f}s")
            return ScrapeResult(
                url=url,
                success=True,
                method=ScrapeMethod.HTTP,
                jobs=jobs,
                duration_seconds=time.time() - start_time
            )
        logger.info("  ❌ HTTP failed or 0 jobs")
        
        # ==========================================
        # Method 3: Playwright (Last Resort)
        # Slow but most reliable fallback
        # ==========================================
        if PLAYWRIGHT_AVAILABLE:
            logger.info("  3️⃣  Trying Playwright (slow but reliable)...")
            jobs = self.playwright_scraper.scrape_site(url)
            if jobs and len(jobs) > 0:
                self.stats['playwright_success'] += 1
                logger.info(f"  ✅ Playwright Success: {len(jobs)} jobs in {time.time() - start_time:.1f}s")
                return ScrapeResult(
                    url=url,
                    success=True,
                    method=ScrapeMethod.PLAYWRIGHT,
                    jobs=jobs,
                    duration_seconds=time.time() - start_time
                )
            logger.info("  ❌ Playwright failed")
        
        # All methods failed
        self.stats['total_failed'] += 1
        logger.warning(f"  ⛔ All 3 methods failed for {url}")
        
        return ScrapeResult(
            url=url,
            success=False,
            error="All methods failed (API + HTTP + Playwright)",
            duration_seconds=time.time() - start_time
        )
    
    def scrape_sites(
        self,
        urls: List[str],
        max_workers: Optional[int] = None
    ) -> Tuple[List[Dict], List[ScrapeResult], Dict]:
        """
        Scrape multiple sites with parallel execution.
        
        Args:
            urls: List of URLs to scrape
            max_workers: Number of parallel workers
            
        Returns:
            Tuple of (all_jobs, results, stats)
        """
        max_workers = max_workers or self.config.max_workers
        
        logger.info(f"Starting scrape of {len(urls)} sites with {max_workers} workers")
        
        start_time = time.time()
        all_jobs = []
        results = []
        checkpointer = Checkpointer('scrape', self.config.checkpoint_interval)
        
        # Load any existing checkpoint
        checkpoint_jobs, checkpoint_count = checkpointer.load_latest()
        if checkpoint_count > 0:
            all_jobs = checkpoint_jobs
            urls = urls[checkpoint_count:]
            logger.info(f"Resuming from checkpoint at {checkpoint_count} sites")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.scrape_site, url): url for url in urls}
            
            with tqdm(total=len(urls), desc="Scraping sites") as pbar:
                for future in as_completed(futures):
                    result = future.result()
                    results.append(result)
                    
                    if result.success:
                        all_jobs.extend(result.jobs)
                    
                    pbar.update(1)
                    pbar.set_postfix({
                        'jobs': len(all_jobs),
                        'success': sum(1 for r in results if r.success)
                    })
                    
                    # Checkpoint
                    current_count = checkpoint_count + len(results)
                    if checkpointer.should_save(current_count):
                        checkpointer.save(all_jobs, current_count)
        
        # Calculate final stats
        elapsed = time.time() - start_time
        
        success_count = sum(1 for r in results if r.success)
        
        final_stats = {
            'execution': {
                'total_sites': len(urls) + checkpoint_count,
                'sites_scraped': len(results) + checkpoint_count,
                'sites_successful': success_count + (checkpoint_count if checkpoint_count else 0),
                'sites_failed': len(results) - success_count,
                'success_rate': success_count / len(results) if results else 0,
                'total_runtime_seconds': elapsed,
                'runtime_formatted': format_duration(elapsed),
            },
            'method_distribution': {
                'http': self.stats['http_success'],
                'api': self.stats['api_success'],
                'playwright': self.stats['playwright_success'],
            },
            'jobs': {
                'total_raw': len(all_jobs),
            },
        }
        
        logger.info(f"Scraping complete: {success_count}/{len(results)} sites successful")
        logger.info(f"Total jobs scraped: {len(all_jobs)}")
        logger.info(f"Runtime: {format_duration(elapsed)}")
        
        return all_jobs, results, final_stats


# ============================================================================
# MAIN PIPELINE
# ============================================================================

def load_domains_from_file(filename: str = 'discovered_domains.txt') -> List[str]:
    """
    Load domains from a text file and convert to URLs.
    
    Args:
        filename: Name of the domains file
        
    Returns:
        List of URLs with /careers path
    """
    input_dir = get_input_dir()
    filepath = input_dir / filename
    
    if not filepath.exists():
        # Try discovered_urls.txt as fallback
        filepath = input_dir / 'discovered_urls.txt'
    
    if not filepath.exists():
        return []
    
    urls = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # Handle both domain names and full URLs
            if line.startswith('http'):
                urls.append(line)
            else:
                # It's a domain, add https:// prefix
                urls.append(f"https://{line}/careers")
    
    return urls


def load_pattern_config() -> Optional[Dict]:
    """
    Load pattern analysis from pattern_analysis.json.
    
    Returns:
        Pattern analysis data or None
    """
    try:
        input_dir = get_input_dir()
        filepath = input_dir / 'pattern_analysis.json'
        
        if filepath.exists():
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.debug(f"Could not load pattern analysis: {e}")
    
    return None


def categorize_test_results(
    results: List[ScrapeResult],
    threshold_days: int = 60
) -> Dict:
    """
    Categorize domains from test run based on job freshness.
    
    Args:
        results: List of ScrapeResult from test scraping
        threshold_days: Days threshold for fresh jobs
        
    Returns:
        Dict with categorized domain lists and statistics
    """
    from datetime import datetime, timedelta
    
    working_domains = []
    stale_domains = []
    broken_domains = []
    
    threshold_date = datetime.now() - timedelta(days=threshold_days)
    
    for result in results:
        if not result.success or not result.jobs:
            # No jobs found or scraping failed
            broken_domains.append(result.url)
            continue
        
        # Find most recent job by date_posted
        most_recent_date = None
        for job in result.jobs:
            date_str = job.get('date_posted')
            if date_str:
                try:
                    # Try parsing common date formats
                    for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ']:
                        try:
                            job_date = datetime.strptime(date_str[:19], fmt)
                            if not most_recent_date or job_date > most_recent_date:
                                most_recent_date = job_date
                            break
                        except ValueError:
                            continue
                except Exception:
                    continue
        
        if most_recent_date:
            # Check if recent job is fresh
            if most_recent_date >= threshold_date:
                working_domains.append(result.url)
            else:
                stale_domains.append(result.url)
        else:
            # No date found - assume working (conservative approach)
            working_domains.append(result.url)
    
    # Calculate statistics
    total_jobs = sum(len(r.jobs) for r in results if r.success)
    avg_jobs_per_working = total_jobs / len(working_domains) if working_domains else 0
    estimated_total = int(avg_jobs_per_working * len(working_domains))
    
    return {
        'working_domains': working_domains,
        'stale_domains': stale_domains,
        'broken_domains': broken_domains,
        'stats': {
            'total_tested': len(results),
            'working_count': len(working_domains),
            'stale_count': len(stale_domains),
            'broken_count': len(broken_domains),
            'total_jobs_in_test': total_jobs,
            'avg_jobs_per_working_domain': round(avg_jobs_per_working, 1),
            'estimated_total_jobs': estimated_total,
            'success_rate': len(working_domains) / len(results) if results else 0,
        }
    }


def run_scraper(
    urls_file: Optional[str] = None,
    domains_file: Optional[str] = None,
    urls: Optional[List[str]] = None,
    config: Optional[ScraperConfig] = None,
    output_prefix: str = 'jobs'
) -> Dict:
    """
    Run the complete scraping pipeline.
    
    Args:
        urls_file: Path to file containing URLs
        domains_file: Path to file containing domains
        urls: List of URLs (alternative to file)
        config: Scraper configuration
        output_prefix: Prefix for output files
        
    Returns:
        Final statistics
    """
    logger.info("=" * 60)
    logger.info("STARTING AVATURE SCRAPER")
    logger.info("=" * 60)
    
    start_time = time.time()
    config = config or ScraperConfig()
    
    # Load pattern analysis for optimization
    pattern_config = load_pattern_config()
    if pattern_config:
        logger.info("Loaded pattern analysis configuration")
        # Could customize config based on pattern_config here
        pagination = pattern_config.get('pagination', {})
        if pagination.get('jobRecordsPerPage_analysis'):
            common_sizes = pagination['jobRecordsPerPage_analysis'].get('most_common', [])
            if common_sizes:
                config.jobs_per_page = common_sizes[0][0]
                logger.info(f"Using page size {config.jobs_per_page} from pattern analysis")
    
    # Load URLs from various sources
    if urls is None:
        if domains_file:
            urls = load_domains_from_file(domains_file)
        elif urls_file:
            urls = load_urls(urls_file)
        else:
            # Try discovered_domains.txt first, then discovered_urls.txt
            urls = load_domains_from_file('discovered_domains.txt')
            if not urls:
                urls = load_urls('discovered_urls.txt')
    
    if not urls:
        logger.error("No URLs to scrape")
        return {'error': 'No URLs provided'}
    
    logger.info(f"Loaded {len(urls)} URLs to scrape")
    
    # Initialize scraper
    scraper = HybridScraper(config)
    
    # Scrape sites
    all_jobs, results, scrape_stats = scraper.scrape_sites(urls)
    
    # If test mode, categorize and save domain lists
    if config.test_one_job_mode:
        logger.info("Test mode: categorizing domains...")
        categorization = categorize_test_results(results, config.test_date_threshold_days)
        
        # Save domain lists
        output_dir = get_output_dir()
        
        # Save working domains
        with open(output_dir / 'working_domains.txt', 'w') as f:
            for url in categorization['working_domains']:
                f.write(f"{url}\n")
        
        # Save stale domains
        with open(output_dir / 'stale_domains.txt', 'w') as f:
            for url in categorization['stale_domains']:
                f.write(f"{url}\n")
        
        # Save broken domains
        with open(output_dir / 'broken_domains.txt', 'w') as f:
            for url in categorization['broken_domains']:
                f.write(f"{url}\n")
        
        # Save test results JSON
        save_json(categorization['stats'], 'test_results.json')
        
        # Log test results
        logger.info("=" * 60)
        logger.info("TEST MODE RESULTS")
        logger.info("=" * 60)
        logger.info(f"Total domains tested: {categorization['stats']['total_tested']}")
        logger.info(f"Working domains: {categorization['stats']['working_count']} ({categorization['stats']['success_rate']:.1%})")
        logger.info(f"Stale domains: {categorization['stats']['stale_count']}")
        logger.info(f"Broken domains: {categorization['stats']['broken_count']}")
        logger.info(f"Average jobs per working domain: {categorization['stats']['avg_jobs_per_working_domain']}")
        logger.info(f"Estimated total jobs if full scrape: {categorization['stats']['estimated_total_jobs']}")
        logger.info("=" * 60)
        logger.info(f"Domain lists saved to: {output_dir}")
        logger.info("  - working_domains.txt (use for full scrape)")
        logger.info("  - stale_domains.txt (has jobs but old)")
        logger.info("  - broken_domains.txt (failed/no jobs)")
        logger.info(f"Test results saved to: {output_dir / 'test_results.json'}")
        
        # Return early - don't do deduplication/validation in test mode
        return categorization['stats']
    
    # Clean jobs
    logger.info("Cleaning job data...")
    all_jobs = clean_jobs_batch(all_jobs)
    
    # Deduplicate
    logger.info("Deduplicating jobs...")
    unique_jobs, dedup_stats = deduplicate_jobs(all_jobs, strategy='hybrid')
    
    # Validate
    logger.info("Validating jobs...")
    valid_jobs, invalid_jobs, validation_stats = validate_jobs(unique_jobs)
    
    # Calculate quality
    quality_stats = calculate_batch_quality(valid_jobs)
    
    # Save outputs
    output_dir = get_output_dir()
    
    if 'json' in config.output_formats:
        save_json(valid_jobs, f'{output_prefix}_clean.json')
    
    if 'csv' in config.output_formats:
        save_csv(valid_jobs, f'{output_prefix}_clean.csv')
    
    if 'jsonl' in config.output_formats:
        save_jsonl(valid_jobs, f'{output_prefix}_clean.jsonl')
    
    # Save failed sites
    failed_sites = [r.url for r in results if not r.success]
    if failed_sites:
        save_json(failed_sites, 'failed_sites.json')
    
    # Compile final stats
    elapsed = time.time() - start_time
    
    final_stats = {
        'timestamp': get_timestamp(),
        'execution': {
            **scrape_stats['execution'],
            'total_pipeline_runtime': format_duration(elapsed),
        },
        'coverage': {
            'total_jobs_raw': len(all_jobs),
            'total_jobs_unique': len(unique_jobs),
            'total_jobs_valid': len(valid_jobs),
            'deduplication_rate': dedup_stats.get('duplicates_removed', 0) / len(all_jobs) if all_jobs else 0,
        },
        'method_distribution': scrape_stats['method_distribution'],
        'deduplication': dedup_stats,
        'validation': validation_stats,
        'quality': quality_stats,
    }
    
    save_json(final_stats, 'scraping_stats.json')
    
    # Log summary
    logger.info("=" * 60)
    logger.info("SCRAPING COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Sites scraped: {scrape_stats['execution']['sites_successful']}/{scrape_stats['execution']['sites_scraped']}")
    logger.info(f"Jobs scraped: {len(all_jobs)} raw → {len(valid_jobs)} valid")
    logger.info(f"Deduplication: {dedup_stats.get('duplicates_removed', 0)} removed")
    logger.info(f"Runtime: {format_duration(elapsed)}")
    logger.info(f"Outputs saved to: {output_dir}")
    
    return final_stats


# ============================================================================
# CLI ENTRY POINT
# ============================================================================

def main():
    """Main entry point for scraper module."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Avature Hybrid Scraper')
    parser.add_argument(
        '--domains-file',
        type=str,
        default='discovered_domains.txt',
        help='Path to file containing domains (one per line)'
    )
    parser.add_argument(
        '--urls-file',
        type=str,
        help='Path to file containing full URLs (alternative to domains)'
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=10,
        help='Number of parallel workers'
    )
    parser.add_argument(
        '--test',
        type=int,
        default=0,
        help='Test mode: scrape only N sites (0 = all)'
    )
    parser.add_argument(
        '--limit', 
        type=int,
        default=0,
        help='Alias for --test: limit to N sites'
    )
    parser.add_argument(
        '--test-one-job',
        action='store_true',
        help='Test mode: scrape only first page from each domain to validate and categorize'
    )
    parser.add_argument(
        '--output-prefix',
        type=str,
        default='jobs',
        help='Prefix for output files'
    )
    
    args = parser.parse_args()
    
    config = ScraperConfig(
        max_workers=args.workers,
        test_one_job_mode=args.test_one_job
    )
    
    # Load URLs from domains or URLs file
    if args.urls_file:
        urls = load_urls(args.urls_file)
    else:
        urls = load_domains_from_file(args.domains_file)
    
    # Handle both --test and --limit
    limit = args.test or args.limit
    if limit > 0:
        logger.info(f"Test mode: scraping {limit} sites")
        urls = urls[:limit]
    
    if not urls:
        logger.error("No URLs found. Make sure discovered_domains.txt or discovered_urls.txt exists in input/")
        return
    
    stats = run_scraper(
        urls=urls,
        config=config,
        output_prefix=args.output_prefix
    )
    
    if 'error' not in stats:
        print(f"\nScraping complete!")
        print(f"Valid jobs: {stats['coverage']['total_jobs_valid']}")
        print(f"Success rate: {stats['execution']['success_rate']:.1%}")
    else:
        print(f"\nScraping failed: {stats['error']}")


if __name__ == '__main__':
    main()
