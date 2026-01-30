"""
HTML Cleaning Module for Avature Scraper.

Provides code-based HTML cleaning without LLM dependencies.
Removes noise while preserving meaningful structure.

Key features:
- Remove scripts, styles, tracking elements
- Preserve semantic structure (lists, paragraphs)
- Remove common noise patterns
- Clean whitespace and formatting
"""

import re
from typing import List, Optional, Tuple
from bs4 import BeautifulSoup, Comment, NavigableString


# ============================================================================
# NOISE PATTERNS
# ============================================================================

# Tags to completely remove (including contents)
REMOVE_TAGS = {
    'script', 'style', 'noscript', 'iframe', 'svg', 'canvas',
    'video', 'audio', 'source', 'track', 'map', 'area',
    'form', 'input', 'button', 'select', 'textarea', 'option',
    'nav', 'footer', 'header', 'aside',
}

# Classes that indicate noise elements
NOISE_CLASS_PATTERNS = [
    'hidden', 'hide', 'invisible', 'offscreen', 'sr-only', 'screen-reader',
    'tracking', 'analytics', 'cookie', 'consent', 'popup', 'modal',
    'advertisement', 'ads', 'sponsor', 'promo', 'banner',
    'social', 'share', 'sharing', 'tweet', 'facebook', 'linkedin',
    'comment', 'comments', 'feedback',
    'sidebar', 'related', 'suggested', 'recommended',
    'newsletter', 'subscribe', 'signup', 'sign-up',
    'tooltip', 'popover', 'dropdown',
]

# Common noise text patterns to remove
NOISE_TEXT_PATTERNS = [
    'Powered by Avature',
    'Share this job',
    'Share job',
    'Apply now',
    'Apply Now',
    'Save job',
    'Save Job',
    'Print job',
    'Print Job',
    'Email this job',
    'Email job',
    'Back to search',
    'Back to results',
    'View all jobs',
    'View all positions',
    'Similar jobs',
    'Related jobs',
    'More positions',
    'Follow us',
    'Connect with us',
    'Join our team',
    'We are hiring',
    'Loading...',
    'Please wait...',
    'Cookie Policy',
    'Privacy Policy',
    'Terms of Use',
    'Terms and Conditions',
    '© ',
    'Copyright ',
    'All rights reserved',
    # Avature-specific navigation noise
    'Welcome!',
    'Sign in',
    'Register',
    '< Back to job list',
    'Back to job list',
    'Ref#:',
    'Date published:',
    'or',  # The "or" between Sign in and Register
]

# Regex patterns for noise
NOISE_REGEX_PATTERNS = [
    r'\b(tweet|share|pin|post)\s+(this|it)\b',
    r'\b(click|tap)\s+here\b',
    r'\b(read|learn)\s+more\b$',
    r'^\s*(loading|please wait)\s*\.{0,3}\s*$',
    r'^\s*\d+\s*(views?|clicks?)\s*$',
    r'^\s*posted\s+\d+\s+(days?|hours?|minutes?)\s+ago\s*$',
    # Avature-specific patterns
    r'^\s*Date published:\s*\d{1,2}-\w{3}-\d{4}\s*$',  # Date published: 12-Jul-2023
    r'^\s*Ref#:\s*\w*\s*$',  # Ref#: (empty or with value)
    r'^<\s*Back to job list\s*$',  # < Back to job list
]


# ============================================================================
# CORE CLEANING FUNCTIONS
# ============================================================================

def remove_unwanted_tags(soup: BeautifulSoup) -> BeautifulSoup:
    """
    Remove tags that should be completely excluded.
    
    Args:
        soup: BeautifulSoup object
        
    Returns:
        Modified soup object
    """
    for tag in soup.find_all(REMOVE_TAGS):
        tag.decompose()
    
    return soup


def remove_comments(soup: BeautifulSoup) -> BeautifulSoup:
    """
    Remove HTML comments.
    
    Args:
        soup: BeautifulSoup object
        
    Returns:
        Modified soup object
    """
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()
    
    return soup


def remove_hidden_elements(soup: BeautifulSoup) -> BeautifulSoup:
    """
    Remove elements hidden via CSS.
    
    Detects:
    - display: none
    - visibility: hidden
    - opacity: 0
    - height: 0
    
    Args:
        soup: BeautifulSoup object
        
    Returns:
        Modified soup object
    """
    hidden_style_patterns = [
        'display:none', 'display: none',
        'visibility:hidden', 'visibility: hidden',
        'opacity:0', 'opacity: 0',
        'height:0', 'height: 0',
    ]
    
    for tag in soup.find_all(style=True):
        style = tag.get('style', '').lower().replace(' ', '')
        if any(pattern.replace(' ', '') in style for pattern in hidden_style_patterns):
            tag.decompose()
    
    # Also remove by common hidden classes
    for tag in soup.find_all(class_=lambda x: x and any(
        pattern in str(x).lower() for pattern in ['hidden', 'hide', 'invisible', 'd-none']
    )):
        tag.decompose()
    
    return soup


def remove_noise_elements(soup: BeautifulSoup) -> BeautifulSoup:
    """
    Remove elements with noise-indicating classes.
    
    Args:
        soup: BeautifulSoup object
        
    Returns:
        Modified soup object
    """
    for tag in soup.find_all(class_=True):
        classes = tag.get('class', [])
        class_str = ' '.join(classes).lower()
        
        if any(pattern in class_str for pattern in NOISE_CLASS_PATTERNS):
            tag.decompose()
    
    return soup


def remove_empty_elements(soup: BeautifulSoup) -> BeautifulSoup:
    """
    Remove empty elements that add no value.
    
    Args:
        soup: BeautifulSoup object
        
    Returns:
        Modified soup object
    """
    # Tags that are ok to be empty
    allowed_empty = {'br', 'hr', 'img', 'input', 'meta', 'link'}
    
    # Multiple passes to handle nested empty elements
    for _ in range(3):
        for tag in soup.find_all():
            if tag.name not in allowed_empty:
                # Check if element has meaningful content
                text = tag.get_text(strip=True)
                has_children = bool(tag.find_all())
                
                if not text and not has_children:
                    tag.decompose()
    
    return soup


def clean_noise_text(text: str) -> str:
    """
    Remove known noise text patterns.
    
    Args:
        text: Text to clean
        
    Returns:
        Cleaned text
    """
    # Remove exact matches
    for pattern in NOISE_TEXT_PATTERNS:
        text = text.replace(pattern, '')
    
    # Remove regex matches
    for pattern in NOISE_REGEX_PATTERNS:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    return text


def clean_whitespace(text: str) -> str:
    """
    Clean up whitespace while preserving structure.
    
    Args:
        text: Text to clean
        
    Returns:
        Cleaned text
    """
    # Replace multiple spaces with single space
    text = re.sub(r'[ \t]+', ' ', text)
    
    # Replace multiple newlines with double newline (paragraph break)
    text = re.sub(r'\n\s*\n+', '\n\n', text)
    
    # Remove leading/trailing whitespace from lines
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(lines)
    
    # Remove empty lines at start/end
    text = text.strip()
    
    return text


def normalize_list_formatting(text: str) -> str:
    """
    Normalize list formatting for consistent output.
    
    Args:
        text: Text to normalize
        
    Returns:
        Normalized text
    """
    # Convert various bullet styles to consistent format
    bullet_patterns = [
        (r'^[\s]*[•●○◦▪▫–—]\s*', '• '),
        (r'^[\s]*[\*\-]\s+', '• '),
        (r'^[\s]*\d+\.\s+', lambda m: m.group(0)),  # Keep numbered lists
    ]
    
    lines = text.split('\n')
    normalized = []
    
    for line in lines:
        for pattern, replacement in bullet_patterns:
            if callable(replacement):
                line = re.sub(pattern, replacement, line, flags=re.MULTILINE)
            else:
                line = re.sub(pattern, replacement, line, flags=re.MULTILINE)
        normalized.append(line)
    
    return '\n'.join(normalized)


# ============================================================================
# MAIN CLEANING FUNCTIONS
# ============================================================================

def clean_html(html_content: str) -> Tuple[str, str]:
    """
    Clean HTML content, returning both text and cleaned HTML.
    
    Removes noise while preserving meaningful structure.
    No LLM dependencies - pure code-based cleaning.
    
    Args:
        html_content: Raw HTML content
        
    Returns:
        Tuple of (cleaned_text, cleaned_html)
    """
    if not html_content:
        return "", ""
    
    # Parse HTML
    soup = BeautifulSoup(html_content, 'lxml')
    
    # Apply cleaning steps in order
    soup = remove_comments(soup)
    soup = remove_unwanted_tags(soup)
    soup = remove_hidden_elements(soup)
    soup = remove_noise_elements(soup)
    soup = remove_empty_elements(soup)
    
    # Get cleaned HTML
    cleaned_html = str(soup)
    
    # Extract text with structure preservation
    text = soup.get_text(separator='\n', strip=True)
    
    # Clean the text
    text = clean_noise_text(text)
    text = clean_whitespace(text)
    text = normalize_list_formatting(text)
    
    return text, cleaned_html


def clean_description(html_content: str) -> str:
    """
    Clean a job description HTML, returning clean text.
    
    Optimized for job description content specifically.
    
    Args:
        html_content: Raw HTML job description
        
    Returns:
        Cleaned text description
    """
    if not html_content:
        return ""
    
    # Parse HTML
    soup = BeautifulSoup(html_content, 'lxml')
    
    # Apply cleaning
    soup = remove_comments(soup)
    soup = remove_unwanted_tags(soup)
    soup = remove_hidden_elements(soup)
    soup = remove_noise_elements(soup)
    
    # Get text with separators
    text = soup.get_text(separator='\n', strip=True)
    
    # Apply text cleaning
    text = clean_noise_text(text)
    text = clean_whitespace(text)
    text = normalize_list_formatting(text)
    
    # Final cleanup
    text = text.strip()
    
    return text


def clean_description_html(html_content: str) -> str:
    """
    Clean job description HTML while preserving structure.
    
    Keeps semantic HTML elements for rich display.
    
    Args:
        html_content: Raw HTML job description
        
    Returns:
        Cleaned HTML
    """
    if not html_content:
        return ""
    
    # Parse HTML
    soup = BeautifulSoup(html_content, 'lxml')
    
    # Apply cleaning
    soup = remove_comments(soup)
    soup = remove_unwanted_tags(soup)
    soup = remove_hidden_elements(soup)
    soup = remove_noise_elements(soup)
    soup = remove_empty_elements(soup)
    
    # Get the cleaned HTML
    cleaned = str(soup)
    
    # Remove excessive whitespace in HTML
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = re.sub(r'>\s+<', '><', cleaned)
    
    return cleaned.strip()


def extract_text_only(html_content: str) -> str:
    """
    Extract plain text from HTML without any formatting.
    
    Args:
        html_content: HTML content
        
    Returns:
        Plain text
    """
    if not html_content:
        return ""
    
    soup = BeautifulSoup(html_content, 'lxml')
    
    # Remove scripts and styles
    for tag in soup.find_all(['script', 'style']):
        tag.decompose()
    
    text = soup.get_text(separator=' ', strip=True)
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


# ============================================================================
# SPECIALIZED CLEANERS
# ============================================================================

def clean_job_title(title: str) -> str:
    """
    Clean and normalize a job title.
    
    Args:
        title: Raw job title
        
    Returns:
        Cleaned title
    """
    if not title:
        return ""
    
    # Remove HTML if present
    title = BeautifulSoup(title, 'lxml').get_text()
    
    # Clean whitespace
    title = re.sub(r'\s+', ' ', title).strip()
    
    # Remove common prefixes/suffixes
    noise = [
        r'^job:\s*',
        r'^position:\s*',
        r'\s*-\s*apply\s*now\s*$',
        r'\s*\(new\)\s*$',
        r'\s*\[new\]\s*$',
    ]
    
    for pattern in noise:
        title = re.sub(pattern, '', title, flags=re.IGNORECASE)
    
    return title.strip()


def clean_location(location: str) -> str:
    """
    Clean and normalize a location string.
    
    Args:
        location: Raw location
        
    Returns:
        Cleaned location
    """
    if not location:
        return ""
    
    # Remove HTML if present
    location = BeautifulSoup(location, 'lxml').get_text()
    
    # Clean whitespace
    location = re.sub(r'\s+', ' ', location).strip()
    
    # Remove common prefixes
    noise = [
        r'^location:\s*',
        r'^loc:\s*',
        r'^office:\s*',
    ]
    
    for pattern in noise:
        location = re.sub(pattern, '', location, flags=re.IGNORECASE)
    
    return location.strip()


def clean_company_name(name: str) -> str:
    """
    Clean and normalize a company name.
    
    Args:
        name: Raw company name
        
    Returns:
        Cleaned name
    """
    if not name:
        return ""
    
    # Remove HTML if present
    name = BeautifulSoup(name, 'lxml').get_text()
    
    # Clean whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    
    # Remove common suffixes
    suffixes = [
        r'\s+(inc\.?|llc\.?|corp\.?|ltd\.?|limited|incorporated|corporation)$',
        r'\s+careers$',
        r'\s+jobs$',
    ]
    
    for pattern in suffixes:
        name = re.sub(pattern, '', name, flags=re.IGNORECASE)
    
    return name.strip()
