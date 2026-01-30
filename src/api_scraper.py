"""
API Scraper Module - FASTEST method for Avature sites.

Advantages:
- 10-20x faster than HTML scraping
- Clean JSON data (no HTML noise)
- Pagination built-in
- Complete job data in single request

Common Avature API Endpoints:
- /SearchJobsData
- /api/jobs
- /services/jobssearchservlet
"""

import json
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

from .utils import setup_logger, get_api_headers, normalize_url

logger = setup_logger('api_scraper', 'api_scraper.log')


class AvatureAPIScaper:
    """Fast API-based scraper for Avature portals."""
    
    # Known Avature API endpoints (in order of prevalence)
    API_ENDPOINTS = [
        '/SearchJobsData',                    # Most common
        '/services/jobssearchservlet',        # Bank of America, etc.
        '/api/jobs',                          # Alternative
        '/careers/SearchJobsData',            # With /careers prefix
        '/en_US/careers/SearchJobsData',      # With locale
        '/PublicReports/SearchReport',        # Hidden JSON API
        '/api/jobsearch',                     # Alternative API endpoint
        '/services/CareerPortal/SearchJobs',  # CareerPortal variant
        '/PublicReports/JobSearch',           # PublicReports variant
        '/api/v1/jobs',                       # REST API v1
    ]
    
    # API pagination patterns
    PAGINATION_PATTERNS = [
        'jobRecordsPerPage={per_page}&jobOffset={offset}',     # Avature standard (98%)
        'limit={per_page}&offset={offset}',                    # REST standard
        'page={page}&per_page={per_page}',                     # Alternative
    ]
    
    def __init__(self, timeout: int = 15):
        self.session = requests.Session()
        self.session.headers.update(get_api_headers())
        self.timeout = timeout
    
    def detect_api_endpoint(self, base_url: str) -> Optional[Tuple[str, Dict]]:
        """
        Detect if portal has an API endpoint.
        
        Returns:
            (endpoint_url, sample_data) if found, None otherwise
        """
        base = base_url.replace('/careers', '').rstrip('/')
        
        for endpoint_path in self.API_ENDPOINTS:
            endpoint_url = base + endpoint_path
            
            try:
                logger.info(f"Testing API: {endpoint_url}")
                response = self.session.get(
                    endpoint_url,
                    timeout=3,
                    params={'jobRecordsPerPage': 10, 'jobOffset': 0}
                )
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        
                        # Validate it's actually job data
                        jobs = self._extract_jobs_from_json(data)
                        if jobs:
                            logger.info(f"✅ API detected: {endpoint_url} ({len(jobs)} jobs found)")
                            return endpoint_url, data
                    except (json.JSONDecodeError, ValueError):
                        continue
                        
            except requests.RequestException as e:
                logger.debug(f"API test failed for {endpoint_url}: {e}")
                continue
        
        logger.info(f"❌ No API endpoint found for {base_url}")
        return None
    
    def scrape_all_jobs(self, base_url: str, endpoint: str, max_jobs: int = 10000) -> List[Dict]:
        """
        Scrape ALL jobs from API with pagination.
        
        Args:
            base_url: Portal base URL (for constructing job URLs)
            endpoint: API endpoint URL
            max_jobs: Maximum jobs to fetch (safety limit)
            
        Returns:
            List of job dictionaries
        """
        all_jobs = []
        page = 0
        jobs_per_page = 50  # API can handle larger page sizes
        consecutive_empty = 0
        
        logger.info(f"Starting API scraping from: {endpoint}")
        
        while len(all_jobs) < max_jobs:
            offset = page * jobs_per_page
            
            # Try different pagination patterns
            for pattern in self.PAGINATION_PATTERNS:
                params_str = pattern.format(
                    per_page=jobs_per_page,
                    offset=offset,
                    page=page + 1
                )
                
                paginated_url = f"{endpoint}?{params_str}"
                
                try:
                    logger.info(f"API page {page + 1}, offset {offset}...")
                    response = self.session.get(paginated_url, timeout=self.timeout)
                    
                    if response.status_code != 200:
                        continue
                    
                    data = response.json()
                    page_jobs = self._extract_jobs_from_json(data)
                    
                    if not page_jobs:
                        continue
                    
                    # Success! Add jobs
                    logger.info(f"✅ API page {page + 1}: {len(page_jobs)} jobs")
                    
                    # Enrich with full details from portal URL
                    for job in page_jobs:
                        # Ensure application_url is absolute
                        if 'application_url' in job and not job['application_url'].startswith('http'):
                            job['application_url'] = urljoin(base_url, job['application_url'])
                        
                        # Add portal_url
                        job['portal_url'] = base_url
                        job['extraction_method'] = 'api'
                    
                    all_jobs.extend(page_jobs)
                    consecutive_empty = 0
                    break  # Success with this pattern, move to next page
                    
                except (requests.RequestException, json.JSONDecodeError) as e:
                    logger.debug(f"API request failed: {e}")
                    continue
            else:
                # No pattern worked for this page
                consecutive_empty += 1
                if consecutive_empty >= 2:
                    logger.info(f"No more jobs found after {page} pages")
                    break
            
            page += 1
            
            # Safety: prevent infinite loops
            if page > 200:  # 200 pages * 50 jobs = 10,000 jobs max
                logger.warning("Reached maximum page limit (200 pages)")
                break
        
        logger.info(f"✅ API scraping complete: {len(all_jobs)} total jobs")
        return all_jobs
    
    def _extract_jobs_from_json(self, data: Dict) -> List[Dict]:
        """
        Extract jobs from JSON response.
        
        Handles various JSON structures:
        - {"jobs": [...]}
        - {"data": [...]}
        - {"requisitionList": [...]}
        - Direct array [...]
        """
        if not data:
            return []
        
        # Try common structures
        for key in ['jobs', 'data', 'requisitionList', 'jobPostings', 'results']:
            if key in data and isinstance(data[key], list):
                return self._parse_job_list(data[key])
        
        # Direct array
        if isinstance(data, list):
            return self._parse_job_list(data)
        
        # Single job object
        if isinstance(data, dict) and ('id' in data or 'jobId' in data or 'title' in data):
            return [self._parse_job_object(data)]
        
        return []
    
    def _parse_job_list(self, jobs_array: List[Dict]) -> List[Dict]:
        """Parse array of job objects."""
        parsed_jobs = []
        
        for job_data in jobs_array:
            if not isinstance(job_data, dict):
                continue
            
            parsed = self._parse_job_object(job_data)
            if parsed:
                parsed_jobs.append(parsed)
        
        return parsed_jobs
    
    def _parse_job_object(self, job: Dict) -> Optional[Dict]:
        """
        Parse single job object from API.
        
        Maps API fields to standard format.
        """
        if not job:
            return None
        
        # Extract job ID (various field names)
        job_id = (
            job.get('id') or 
            job.get('jobId') or 
            job.get('requisitionId') or 
            job.get('job_id') or
            job.get('Id')
        )
        
        # Extract title
        title = (
            job.get('title') or 
            job.get('jobTitle') or 
            job.get('positionTitle') or
            job.get('Title')
        )
        
        if not title:
            return None  # Must have at least a title
        
        # Build standardized job object
        parsed = {
            'title': str(title).strip(),
            'job_id': str(job_id) if job_id else None,
            'company_name': self._extract_field(job, ['company', 'companyName', 'employer']),
            'location': self._extract_field(job, ['location', 'jobLocation', 'city', 'primaryLocation']),
            'description': self._extract_field(job, ['description', 'jobDescription', 'summary']),
            'date_posted': self._extract_field(job, ['datePosted', 'postedDate', 'date', 'postingDate']),
            'employment_type': self._extract_field(job, ['employmentType', 'jobType', 'type']),
            'experience_level': self._extract_field(job, ['experienceLevel', 'level', 'seniorityLevel']),
            'remote_type': self._extract_field(job, ['remote', 'remoteType', 'workLocation']),
            'department': self._extract_field(job, ['department', 'team', 'category']),
            'salary_range': self._extract_field(job, ['salary', 'salaryRange', 'compensation']),
        }
        
        # Extract application URL
        application_url = (
            job.get('url') or 
            job.get('applyUrl') or 
            job.get('jobUrl') or
            job.get('link') or
            f"/JobDetail/{job_id}" if job_id else None
        )
        parsed['application_url'] = application_url
        
        # Remove None values
        parsed = {k: v for k, v in parsed.items() if v is not None}
        
        return parsed
    
    def _extract_field(self, job: Dict, field_names: List[str]) -> Optional[str]:
        """Extract field trying multiple possible names."""
        for name in field_names:
            value = job.get(name)
            if value:
                # Handle nested objects
                if isinstance(value, dict):
                    # Try common nested fields
                    value = value.get('name') or value.get('value') or value.get('text')
                
                if value and isinstance(value, str):
                    return value.strip()
        
        return None


def test_api_scraper():
    """Quick test of API scraper."""
    scraper = AvatureAPIScaper()
    
    # Test portals
    test_portals = [
        'https://careers.bankofamerica.com',
        'https://uclahealth.avature.net/careers',
        'https://abbvie.avature.net/careers',
    ]
    
    for portal in test_portals:
        print(f"\n{'='*70}")
        print(f"Testing: {portal}")
        print(f"{'='*70}")
        
        result = scraper.detect_api_endpoint(portal)
        if result:
            endpoint, sample = result
            print(f"✅ API found: {endpoint}")
            
            # Try scraping first page
            jobs = scraper.scrape_all_jobs(portal, endpoint, max_jobs=10)
            print(f"✅ Scraped {len(jobs)} jobs")
            
            if jobs:
                print(f"\nSample job:")
                import pprint
                pprint.pprint(jobs[0])
        else:
            print(f"❌ No API detected")


if __name__ == '__main__':
    test_api_scraper()
