"""
Field Extraction Module for Avature Scraper.

Extracts 14 fields from job listings:
- 5 required fields (title, description, URL, etc.)
- 9 metadata fields (for differentiation)

Key features:
- Multi-selector fallback strategy
- JSON-LD structured data extraction
- Pattern-based inference for employment types
"""

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .cleaner import (
    clean_description,
    clean_description_html,
    clean_job_title,
    clean_location,
    clean_company_name,
)
from .utils import (
    extract_job_id_from_url,
    extract_company_name as extract_company_from_domain,
    get_timestamp,
    setup_logger,
)


logger = setup_logger('extractors')


# ============================================================================
# SELECTOR PATTERNS
# ============================================================================

# Avature-specific fingerprints for detection
# Enhanced patterns from Playwright-based detector for better accuracy
AVATURE_FINGERPRINTS = {
    'js_namespace': r'window\.avature\s*=|Avature\.CareerPortal|avatureConfig|AvatureCareerPortal',
    'data_attributes': r'data-avature-|data-avature-application|data-avature-job',
    'form_patterns': r'jobOffset|jobSearchInterval|__Avature_Redirect_|jobRecordsPerPage',
    'api_endpoints': r'/PublicReports/|/api/jobsearch|/services/CareerPortal|/SearchJobsData',
    'cdn_references': r'avature\.net/Scripts/|avature\.net/Content/|avature\.net/css/',
    'css_classes': r'avature-|jobInfo|jobDescription|banner__text__title',
}

# Title selectors - UNIVERSAL for all Avature sites
TITLE_SELECTORS = [
    # UCLA/newer Avature structure (specific selectors first)
    ('h2', {'class_': lambda x: x and 'banner__text__title' in str(x).lower()}),
    ('h2', {'class_': lambda x: x and 'banner' in str(x).lower() and 'title' in str(x).lower()}),
    
    # Bloomberg/older Avature structure
    ('h1', {'class_': lambda x: x and 'title' in str(x).lower()}),
    ('h2', {'class_': lambda x: x and 'title' in str(x).lower()}),
    ('h3', {'class_': lambda x: x and 'title' in str(x).lower()}),
    ('*', {'class_': lambda x: x and 'job-title' in str(x).lower()}),
    ('*', {'class_': lambda x: x and 'jobtitle' in str(x).lower()}),
    ('*', {'class_': lambda x: x and 'position-title' in str(x).lower()}),
    ('[itemprop="title"]', {}),
    
    # Generic fallbacks (universal)
    ('h1', {}),
    ('h2', {}),
]

# Location selectors - UNIVERSAL for all Avature sites
LOCATION_SELECTORS = [
    # UCLA/newer Avature structure (field-value pairs)
    ('div', {'class_': lambda x: x and 'article__content__view__field__value' in str(x).lower()}),
    ('div', {'class_': lambda x: x and 'field__value' in str(x).lower() and 'location' in str(x).lower()}),
    
    # Bloomberg/older Avature structure
    ('*', {'class_': 'jobInfo'}),  # Avature job metadata container
    ('*', {'class_': lambda x: x and 'location' in str(x).lower()}),
    ('*', {'class_': lambda x: x and 'job-location' in str(x).lower()}),
    ('[itemprop="jobLocation"]', {}),
    ('[itemprop="addressLocality"]', {}),
    
    # Generic fallbacks (universal)
    ('*', {'class_': lambda x: x and 'address' in str(x).lower()}),
    ('*', {'class_': lambda x: x and 'city' in str(x).lower()}),
]

# Description selectors - UNIVERSAL for all Avature sites
DESCRIPTION_SELECTORS = [
    # UCLA/newer Avature structure (specific selectors first)
    ('article', {'class_': lambda x: x and 'article--details' in str(x).lower()}),
    ('div', {'class_': lambda x: x and 'article__content' in str(x).lower()}),
    ('div', {'class_': lambda x: x and 'main__content' in str(x).lower()}),
    ('div', {'class_': lambda x: x and 'section__content' in str(x).lower()}),
    
    # Bloomberg/older Avature structure
    ('*', {'class_': 'jobDescription'}),  # Exact match for Avature
    ('*', {'class_': lambda x: x and 'jobdescription clearer' in str(x).lower()}),
    ('*', {'class_': lambda x: x and 'job-description' in str(x).lower()}),
    ('*', {'class_': lambda x: x and 'jobdescription' in str(x).lower()}),
    ('*', {'class_': lambda x: x and 'description' in str(x).lower()}),
    ('[itemprop="description"]', {}),
    
    # Generic fallbacks (universal)
    ('*', {'class_': lambda x: x and 'content' in str(x).lower()}),
    ('article', {}),
    ('.job-details', {}),
    ('.job-body', {}),
]

# Department selectors
DEPARTMENT_SELECTORS = [
    ('*', {'class_': lambda x: x and 'department' in str(x).lower()}),
    ('*', {'class_': lambda x: x and 'category' in str(x).lower()}),
    ('*', {'class_': lambda x: x and 'team' in str(x).lower()}),
    ('*', {'class_': lambda x: x and 'function' in str(x).lower()}),
    ('[itemprop="industry"]', {}),
]

# Employment type patterns for inference
EMPLOYMENT_TYPE_PATTERNS = {
    'full-time': [r'\bfull[-\s]?time\b', r'\bft\b', r'\bpermanent\b'],
    'part-time': [r'\bpart[-\s]?time\b', r'\bpt\b'],
    'contract': [r'\bcontract\b', r'\bcontractor\b', r'\bfreelance\b', r'\bconsultant\b'],
    'temporary': [r'\btemporary\b', r'\btemp\b', r'\bseasonal\b'],
    'internship': [r'\bintern\b', r'\binternship\b', r'\bstudent\b', r'\bco-?op\b'],
}

# Remote type patterns
REMOTE_TYPE_PATTERNS = {
    'remote': [r'\bremote\b', r'\bwork from home\b', r'\bwfh\b', r'\btelecommute\b', r'\btelework\b'],
    'hybrid': [r'\bhybrid\b', r'\bflexible\b.*\b(location|work)\b', r'\b(location|work)\b.*\bflexible\b'],
    'onsite': [r'\bon[-\s]?site\b', r'\bin[-\s]?office\b', r'\bin[-\s]?person\b'],
}

# Experience level patterns
EXPERIENCE_LEVEL_PATTERNS = {
    'entry': [r'\bentry[-\s]?level\b', r'\bjunior\b', r'\bgraduate\b', r'\b0[-\s]?[–-]?[-\s]?2\s*years?\b'],
    'mid': [r'\bmid[-\s]?level\b', r'\b2[-\s]?[–-]?[-\s]?5\s*years?\b', r'\bintermediate\b'],
    'senior': [r'\bsenior\b', r'\bsr\.?\b', r'\b5[-\s]?\+?\s*years?\b', r'\blead\b', r'\bprincipal\b'],
    'executive': [r'\bexecutive\b', r'\bdirector\b', r'\bvp\b', r'\bc[-\s]?level\b', r'\bchief\b'],
}

# Salary patterns
SALARY_PATTERNS = [
    r'\$[\d,]+\s*[-–]\s*\$[\d,]+',  # $50,000 - $70,000
    r'\$[\d,]+\s*(?:k|K)',  # $50K
    r'[\d,]+\s*[-–]\s*[\d,]+\s*(?:USD|EUR|GBP)',  # 50,000 - 70,000 USD
    r'(?:salary|pay|compensation):\s*\$?[\d,]+',  # salary: $50,000
]


# ============================================================================
# AVATURE DETECTION
# ============================================================================

def detect_avature_site(soup: BeautifulSoup, url: str, html_text: Optional[str] = None) -> Tuple[bool, List[str]]:
    """
    Detect if a page is an Avature site using enhanced fingerprints.
    
    Args:
        soup: BeautifulSoup object
        url: Page URL
        html_text: Optional raw HTML text (for faster regex search)
        
    Returns:
        Tuple of (is_avature, detection_methods)
    """
    detections = []
    
    # Check 1: Explicit URL pattern
    if 'avature.net' in url.lower() or 'avature.cn' in url.lower():
        detections.append("explicit_url")
    
    # Get HTML text for pattern matching
    if html_text is None:
        html_text = str(soup).lower()
    else:
        html_text = html_text.lower()
    
    # Check 2: JavaScript namespace patterns
    if re.search(AVATURE_FINGERPRINTS['js_namespace'], html_text, re.IGNORECASE):
        detections.append("js_namespace")
    
    # Check 3: Form patterns (jobOffset, etc.)
    if re.search(AVATURE_FINGERPRINTS['form_patterns'], html_text, re.IGNORECASE):
        detections.append("form_patterns")
    
    # Check 4: Data attributes
    if re.search(AVATURE_FINGERPRINTS['data_attributes'], html_text, re.IGNORECASE):
        detections.append("data_attributes")
    
    # Check 5: CDN references
    if re.search(AVATURE_FINGERPRINTS['cdn_references'], html_text, re.IGNORECASE):
        detections.append("cdn_references")
    
    # Check 6: Avature-specific CSS classes
    if re.search(AVATURE_FINGERPRINTS['css_classes'], html_text, re.IGNORECASE):
        detections.append("css_classes")
    
    # Check 7: API endpoints in links/scripts
    if re.search(AVATURE_FINGERPRINTS['api_endpoints'], html_text, re.IGNORECASE):
        detections.append("api_endpoints")
    
    # Calculate confidence score
    # Threshold: 2 or more detections = likely Avature
    is_avature = len(detections) >= 2
    
    return is_avature, detections


# ============================================================================
# MULTI-SELECTOR EXTRACTION
# ============================================================================

def find_with_selectors(
    soup: BeautifulSoup,
    selectors: List[Tuple],
    extract_text: bool = True
) -> Optional[str]:
    """
    Try multiple selectors until one finds content.
    
    Args:
        soup: BeautifulSoup object to search
        selectors: List of (tag, attrs) tuples
        extract_text: Whether to extract text (vs return element)
        
    Returns:
        Extracted content or None
    """
    for tag, attrs in selectors:
        try:
            if tag.startswith('[') or '.' in tag or '#' in tag:
                # CSS selector
                elements = soup.select(tag)
            else:
                # BeautifulSoup find
                elements = soup.find_all(tag, **attrs) if attrs else soup.find_all(tag)
            
            for element in elements:
                if element:
                    if extract_text:
                        text = element.get_text(strip=True)
                        if text and len(text) > 2:  # Filter out empty/tiny results
                            return text
                    else:
                        return element
        except Exception:
            continue
    
    return None


# ============================================================================
# JSON-LD EXTRACTION (SECRET WEAPON)
# ============================================================================

def extract_jsonld_data(soup: BeautifulSoup) -> Optional[Dict]:
    """
    Extract structured data from JSON-LD scripts.
    
    Many Avature sites have hidden JobPosting structured data
    that provides clean, standardized field values.
    This is a competitive advantage - most scrapers miss this.
    
    Args:
        soup: BeautifulSoup object
        
    Returns:
        Extracted data dict or None
    """
    scripts = soup.find_all('script', type='application/ld+json')
    
    for script in scripts:
        try:
            if not script.string:
                continue
            
            data = json.loads(script.string)
            
            # Handle arrays (some sites wrap in array)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get('@type') == 'JobPosting':
                        return parse_job_posting_jsonld(item)
            elif isinstance(data, dict):
                if data.get('@type') == 'JobPosting':
                    return parse_job_posting_jsonld(data)
                # Check for @graph structure
                if '@graph' in data:
                    for item in data['@graph']:
                        if isinstance(item, dict) and item.get('@type') == 'JobPosting':
                            return parse_job_posting_jsonld(item)
        except (json.JSONDecodeError, AttributeError):
            continue
    
    return None


def parse_job_posting_jsonld(data: Dict) -> Dict:
    """
    Parse JobPosting JSON-LD into our field format.
    
    Args:
        data: JSON-LD JobPosting object
        
    Returns:
        Parsed fields dict
    """
    result = {}
    
    # Title
    result['title'] = data.get('title') or data.get('name')
    
    # Description
    result['description'] = data.get('description')
    
    # Date posted
    result['date_posted'] = data.get('datePosted')
    
    # Valid through (expiration)
    result['valid_through'] = data.get('validThrough')
    
    # Employment type
    emp_type = data.get('employmentType')
    if emp_type:
        if isinstance(emp_type, list):
            result['employment_type'] = ', '.join(emp_type)
        else:
            result['employment_type'] = emp_type
    
    # Location
    location = data.get('jobLocation')
    if location:
        if isinstance(location, dict):
            address = location.get('address', {})
            if isinstance(address, dict):
                parts = [
                    address.get('addressLocality'),
                    address.get('addressRegion'),
                    address.get('addressCountry'),
                ]
                result['location'] = ', '.join(p for p in parts if p)
            elif isinstance(address, str):
                result['location'] = address
        elif isinstance(location, list) and location:
            # Multiple locations
            locations = []
            for loc in location:
                if isinstance(loc, dict):
                    address = loc.get('address', {})
                    if isinstance(address, dict):
                        parts = [
                            address.get('addressLocality'),
                            address.get('addressRegion'),
                        ]
                        locations.append(', '.join(p for p in parts if p))
            result['location'] = ' | '.join(locations)
    
    # Check for remote work
    job_location_type = data.get('jobLocationType')
    if job_location_type == 'TELECOMMUTE':
        result['remote_type'] = 'Remote'
    
    # Salary
    salary = data.get('baseSalary')
    if salary:
        if isinstance(salary, dict):
            value = salary.get('value', {})
            if isinstance(value, dict):
                min_val = value.get('minValue')
                max_val = value.get('maxValue')
                unit = value.get('unitText', '')
                currency = salary.get('currency', '$')
                if min_val and max_val:
                    result['salary_range'] = f"{currency}{min_val:,} - {currency}{max_val:,} {unit}".strip()
                elif min_val:
                    result['salary_range'] = f"{currency}{min_val:,}+ {unit}".strip()
            elif isinstance(value, (int, float)):
                currency = salary.get('currency', '$')
                result['salary_range'] = f"{currency}{value:,}"
    
    # Company/organization
    org = data.get('hiringOrganization')
    if org:
        if isinstance(org, dict):
            result['company_name'] = org.get('name')
        elif isinstance(org, str):
            result['company_name'] = org
    
    # Experience requirements
    experience = data.get('experienceRequirements')
    if experience:
        if isinstance(experience, dict):
            result['experience_level'] = experience.get('name')
        elif isinstance(experience, str):
            result['experience_level'] = experience
    
    # Industry/department
    result['department'] = data.get('industry') or data.get('occupationalCategory')
    
    return {k: v for k, v in result.items() if v}


# ============================================================================
# FIELD EXTRACTION FUNCTIONS
# ============================================================================

def extract_title(soup: BeautifulSoup, jsonld: Optional[Dict] = None) -> Optional[str]:
    """
    Extract job title with multi-selector fallback.
    UNIVERSAL for all Avature sites (Bloomberg, UCLA, etc.)
    
    Args:
        soup: BeautifulSoup object
        jsonld: Optional JSON-LD data
        
    Returns:
        Cleaned title or None
    """
    # Try JSON-LD first (most reliable)
    if jsonld and jsonld.get('title'):
        return clean_job_title(jsonld['title'])
    
    # Try selectors (includes both Bloomberg and UCLA structures)
    title = find_with_selectors(soup, TITLE_SELECTORS)
    if title:
        return clean_job_title(title)
    
    # UNIVERSAL FALLBACK: Try meta tags (works for all Avature sites)
    meta_tags = [
        soup.find('meta', {'property': 'og:title'}),  # Open Graph
        soup.find('meta', {'name': 'title'}),  # Standard meta
        soup.find('meta', {'name': 'twitter:title'}),  # Twitter cards
    ]
    
    for meta in meta_tags:
        if meta and meta.get('content'):
            content = meta.get('content', '').strip()
            if content and content not in ['Home Page', 'Career Site']:
                return clean_job_title(content)
    
    # Fallback: page title
    page_title = soup.find('title')
    if page_title:
        title_text = page_title.get_text(strip=True)
        # Often formatted as "Job Title - Company Name"
        if ' - ' in title_text:
            return clean_job_title(title_text.split(' - ')[0])
        if ' | ' in title_text:
            return clean_job_title(title_text.split(' | ')[0])
        return clean_job_title(title_text)
    
    return None


def extract_description(soup: BeautifulSoup, jsonld: Optional[Dict] = None) -> Tuple[str, str]:
    """
    Extract job description (text and HTML).
    
    Args:
        soup: BeautifulSoup object
        jsonld: Optional JSON-LD data
        
    Returns:
        Tuple of (cleaned_text, cleaned_html)
    """
    # Try JSON-LD first
    if jsonld and jsonld.get('description'):
        desc_html = jsonld['description']
        desc_text = clean_description(desc_html)
        return desc_text, clean_description_html(desc_html)
    
    # Try selectors
    for tag, attrs in DESCRIPTION_SELECTORS:
        try:
            if tag.startswith('[') or '.' in tag or '#' in tag:
                elements = soup.select(tag)
            else:
                elements = soup.find_all(tag, **attrs) if attrs else soup.find_all(tag)
            
            for element in elements:
                html = str(element)
                text = clean_description(html)
                
                # Filter out too-short descriptions
                if len(text) > 100:
                    return text, clean_description_html(html)
        except Exception:
            continue
    
    # Fallback: main content area
    main = soup.find('main') or soup.find('article') or soup.find('body')
    if main:
        html = str(main)
        text = clean_description(html)
        if len(text) > 100:
            return text, clean_description_html(html)
    
    return "", ""


def extract_location(soup: BeautifulSoup, jsonld: Optional[Dict] = None) -> Optional[str]:
    """
    Extract job location with pattern-based fallback.
    
    Args:
        soup: BeautifulSoup object
        jsonld: Optional JSON-LD data
        
    Returns:
        Cleaned location or None
    """
    # Try JSON-LD first
    if jsonld and jsonld.get('location'):
        return clean_location(jsonld['location'])
    
    # AVATURE-SPECIFIC: Try jobInfo div (priority for Avature detail pages)
    job_info = soup.find('div', class_='jobInfo')
    if job_info:
        text = job_info.get_text()
        # Location is the first line before "Ref#"
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        if lines and not lines[0].startswith('Ref'):
            location = lines[0]
            # Validate it looks like a location (has comma or common location words)
            if ',' in location or any(word in location.lower() for word in ['city', 'state', 'remote', 'usa', 'united']):
                return clean_location(location)
    
    # Try standard selectors
    location = find_with_selectors(soup, LOCATION_SELECTORS)
    if location:
        return clean_location(location)
    
    # Fallback: Parse from text content (e.g., "Work Location: Los Angeles, CA")
    text = soup.get_text()
    location_patterns = [
        r'Work Location:\s*([^\n]+)',
        r'Location:\s*([^\n]+)',
        r'Job Location:\s*([^\n]+)',
        r'Office Location:\s*([^\n]+)',
    ]
    
    for pattern in location_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            loc = match.group(1).strip()
            # Clean up common suffixes
            loc = re.sub(r',?\s+(USA|United States|US)$', '', loc)
            if len(loc) > 3 and len(loc) < 100:
                return clean_location(loc)
    
    return None


def extract_department(soup: BeautifulSoup, jsonld: Optional[Dict] = None) -> Optional[str]:
    """
    Extract department/category.
    
    Args:
        soup: BeautifulSoup object
        jsonld: Optional JSON-LD data
        
    Returns:
        Department or None
    """
    # Try JSON-LD first
    if jsonld and jsonld.get('department'):
        return jsonld['department']
    
    # Try selectors
    return find_with_selectors(soup, DEPARTMENT_SELECTORS)


def infer_employment_type(text: str) -> Optional[str]:
    """
    Infer employment type from text using patterns.
    
    Args:
        text: Text to search (title + description)
        
    Returns:
        Employment type or None
    """
    text_lower = text.lower()
    
    for emp_type, patterns in EMPLOYMENT_TYPE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return emp_type.replace('-', ' ').title()
    
    return None


def infer_remote_type(text: str, jsonld: Optional[Dict] = None) -> Optional[str]:
    """
    Infer remote work type from text.
    
    Args:
        text: Text to search
        jsonld: Optional JSON-LD data
        
    Returns:
        Remote type or None
    """
    # Check JSON-LD first
    if jsonld and jsonld.get('remote_type'):
        return jsonld['remote_type']
    
    text_lower = text.lower()
    
    for remote_type, patterns in REMOTE_TYPE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return remote_type.title()
    
    return None


def infer_experience_level(text: str, jsonld: Optional[Dict] = None) -> Optional[str]:
    """
    Infer experience level from text.
    
    Args:
        text: Text to search
        jsonld: Optional JSON-LD data
        
    Returns:
        Experience level or None
    """
    # Check JSON-LD first
    if jsonld and jsonld.get('experience_level'):
        return jsonld['experience_level']
    
    text_lower = text.lower()
    
    for level, patterns in EXPERIENCE_LEVEL_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return level.title()
    
    return None


def extract_salary(text: str, jsonld: Optional[Dict] = None) -> Optional[str]:
    """
    Extract salary range from text.
    
    Args:
        text: Text to search
        jsonld: Optional JSON-LD data
        
    Returns:
        Salary range or None
    """
    # Check JSON-LD first
    if jsonld and jsonld.get('salary_range'):
        return jsonld['salary_range']
    
    for pattern in SALARY_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0)
    
    return None


def extract_date_posted(soup: BeautifulSoup, jsonld: Optional[Dict] = None) -> Optional[str]:
    """
    Extract job posting date with pattern-based fallback.
    
    Args:
        soup: BeautifulSoup object
        jsonld: Optional JSON-LD data
        
    Returns:
        Date string or None
    """
    # Check JSON-LD first (most reliable)
    if jsonld and jsonld.get('date_posted'):
        return jsonld['date_posted']
    
    # AVATURE-SPECIFIC: Try jobInfo div (priority for Avature detail pages)
    job_info = soup.find('div', class_='jobInfo')
    if job_info:
        text = job_info.get_text()
        # Look for "Date published:" pattern
        date_match = re.search(r'Date published:\s*(\d{1,2}-\w{3}-\d{4})', text, re.IGNORECASE)
        if date_match:
            return date_match.group(1)
    
    # Try common date selectors
    date_selectors = [
        ('*', {'class_': lambda x: x and 'date' in str(x).lower()}),
        ('*', {'class_': lambda x: x and 'posted' in str(x).lower()}),
        ('time', {}),
        ('[itemprop="datePosted"]', {}),
    ]
    
    date_text = find_with_selectors(soup, date_selectors)
    if date_text:
        return date_text
    
    # Fallback: Parse from text content (e.g., "Posted Date\n01/27/2026")
    text = soup.get_text()
    date_patterns = [
        r'Date published[:\s]+(\d{1,2}-\w{3}-\d{4})',  # Avature format: 3-Mar-2017
        r'Posted Date[:\s]+(\d{1,2}/\d{1,2}/\d{4})',
        r'Date Posted[:\s]+(\d{1,2}/\d{1,2}/\d{4})',
        r'Posted[:\s]+(\d{1,2}/\d{1,2}/\d{4})',
        r'Posted Date[:\s]+(\d{4}-\d{2}-\d{2})',
        r'Date Posted[:\s]+(\d{4}-\d{2}-\d{2})',
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    
    return None


# ============================================================================
# MAIN EXTRACTION FUNCTION
# ============================================================================

def extract_job_data(
    soup: BeautifulSoup,
    url: str,
    base_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Extract all 14 fields from a job page.
    
    Fields extracted:
    - REQUIRED: job_id, title, description, description_html, application_url
    - METADATA: company_name, location, remote_type, employment_type,
                department, experience_level, salary_range, date_posted, date_scraped
    
    Args:
        soup: BeautifulSoup object of job page
        url: Job URL
        base_url: Optional base URL for relative links
        
    Returns:
        Dictionary with all extracted fields
    """
    base_url = base_url or url
    
    # First, try JSON-LD extraction (secret weapon)
    jsonld = extract_jsonld_data(soup)
    
    # Extract description first (needed for inference)
    description_text, description_html = extract_description(soup, jsonld)
    
    # Extract title
    title = extract_title(soup, jsonld)
    
    # Combined text for inference
    combined_text = f"{title or ''} {description_text}"
    
    # Build job data
    job_data = {
        # REQUIRED FIELDS (5)
        'job_id': extract_job_id_from_url(url),
        'title': title,
        'description': description_text,
        'description_html': description_html,
        'application_url': url,
        
        # METADATA FIELDS (9)
        'company_name': (
            jsonld.get('company_name') if jsonld and jsonld.get('company_name')
            else extract_company_from_domain(url)
        ),
        'location': extract_location(soup, jsonld),
        'remote_type': infer_remote_type(combined_text, jsonld),
        'employment_type': (
            jsonld.get('employment_type') if jsonld 
            else infer_employment_type(combined_text)
        ),
        'department': extract_department(soup, jsonld),
        'experience_level': infer_experience_level(combined_text, jsonld),
        'salary_range': extract_salary(combined_text, jsonld),
        'date_posted': extract_date_posted(soup, jsonld),
        # Note: date_scraped removed per user request
        # Only keep date_posted (job posting date, not our scrape timestamp)
    }
    
    # Log extraction quality
    filled_fields = sum(1 for v in job_data.values() if v)
    logger.debug(f"Extracted {filled_fields}/14 fields from {url}")
    
    return job_data


def extract_jobs_from_listing(
    soup: BeautifulSoup,
    base_url: str
) -> List[Dict]:
    """
    Extract multiple jobs from a listing page.
    
    Args:
        soup: BeautifulSoup object of listing page
        base_url: Base URL for relative links
        
    Returns:
        List of partial job data (mainly URLs and titles)
    """
    jobs = []
    
    # Common job card selectors
    card_selectors = [
        '[class*="job-card"]',
        '[class*="job-item"]',
        '[class*="job-listing"]',
        '[class*="position-card"]',
        '[class*="vacancy"]',
        'article[class*="job"]',
        '.job-result',
        '.search-result',
    ]
    
    for selector in card_selectors:
        cards = soup.select(selector)
        if cards:
            for card in cards:
                job = extract_job_from_card(card, base_url)
                if job and job.get('application_url'):
                    jobs.append(job)
            break
    
    # Fallback: look for links with job patterns (including Avature variants)
    if not jobs:
        # Updated pattern to include FolderDetail (used by Maximus and others)
        job_links = soup.find_all('a', href=re.compile(r'JobDetail|FolderDetail|/job/|/position/|/careers/Apply/', re.I))
        for link in job_links:
            href = link.get('href', '')
            if href:
                full_url = urljoin(base_url, href)
                title = link.get_text(strip=True)
                if title and len(title) > 3:
                    jobs.append({
                        'title': clean_job_title(title),
                        'application_url': full_url,
                        'job_id': extract_job_id_from_url(full_url),
                    })
    
    return jobs


def extract_job_from_card(card: BeautifulSoup, base_url: str) -> Optional[Dict]:
    """
    Extract job data from a listing card element.
    
    Args:
        card: BeautifulSoup element for job card
        base_url: Base URL for relative links
        
    Returns:
        Partial job data or None
    """
    job = {}
    
    # Find title and link
    title_link = card.find('a', href=True)
    if title_link:
        href = title_link.get('href', '')
        job['application_url'] = urljoin(base_url, href)
        job['job_id'] = extract_job_id_from_url(job['application_url'])
        
        # Title might be in link or separate
        title_elem = card.find(['h1', 'h2', 'h3', 'h4']) or title_link
        job['title'] = clean_job_title(title_elem.get_text(strip=True))
    
    # Location
    loc_elem = card.find(class_=lambda x: x and 'location' in str(x).lower())
    if loc_elem:
        job['location'] = clean_location(loc_elem.get_text(strip=True))
    
    # Department
    dept_elem = card.find(class_=lambda x: x and any(
        term in str(x).lower() for term in ['department', 'category', 'team']
    ))
    if dept_elem:
        job['department'] = dept_elem.get_text(strip=True)
    
    return job if job.get('application_url') else None
