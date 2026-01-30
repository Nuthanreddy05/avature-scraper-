"""
Data Validation Module for Avature Scraper.

Provides validation and quality checks for scraped job data.
Ensures data integrity and catches scraping errors.
"""

import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from .utils import setup_logger, is_avature_url


logger = setup_logger('validator')


# ============================================================================
# VALIDATION RULES
# ============================================================================

# Required fields that must be present and non-empty
REQUIRED_FIELDS = ['title', 'application_url']

# Optional but important fields
IMPORTANT_FIELDS = ['description', 'job_id', 'company_name', 'location']

# All expected fields
ALL_FIELDS = [
    'job_id', 'title', 'description', 'description_html', 'application_url',
    'company_name', 'location', 'remote_type', 'employment_type',
    'department', 'experience_level', 'salary_range', 'date_posted', 'date_scraped'
]

# Minimum lengths for text fields
MIN_LENGTHS = {
    'title': 3,
    'description': 50,
    'company_name': 2,
    'location': 2,
}

# Maximum lengths for text fields
MAX_LENGTHS = {
    'title': 500,
    'description': 50000,
    'company_name': 200,
    'location': 500,
}


# ============================================================================
# FIELD VALIDATORS
# ============================================================================

def validate_url(url: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a URL.
    
    Args:
        url: URL to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not url:
        return False, "URL is empty"
    
    if not isinstance(url, str):
        return False, "URL is not a string"
    
    try:
        parsed = urlparse(url)
        
        if not parsed.scheme:
            return False, "URL missing scheme (http/https)"
        
        if parsed.scheme not in ('http', 'https'):
            return False, f"Invalid URL scheme: {parsed.scheme}"
        
        if not parsed.netloc:
            return False, "URL missing domain"
        
        return True, None
        
    except Exception as e:
        return False, f"URL parsing error: {str(e)}"


def validate_title(title: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a job title.
    
    Args:
        title: Title to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not title:
        return False, "Title is empty"
    
    if not isinstance(title, str):
        return False, "Title is not a string"
    
    if len(title) < MIN_LENGTHS.get('title', 3):
        return False, f"Title too short (min {MIN_LENGTHS['title']} chars)"
    
    if len(title) > MAX_LENGTHS.get('title', 500):
        return False, f"Title too long (max {MAX_LENGTHS['title']} chars)"
    
    # Check for garbage/noise titles
    garbage_patterns = [
        r'^[\d\s\-_\.]+$',  # Only numbers/punctuation
        r'^(null|undefined|none|n/a)$',  # Null values
        r'^loading',  # Loading states
        r'^error',  # Error messages
    ]
    
    title_lower = title.lower().strip()
    for pattern in garbage_patterns:
        if re.match(pattern, title_lower, re.IGNORECASE):
            return False, f"Title appears to be garbage: {title[:50]}"
    
    return True, None


def validate_description(description: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a job description.
    
    Args:
        description: Description to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not description:
        return False, "Description is empty"
    
    if not isinstance(description, str):
        return False, "Description is not a string"
    
    if len(description) < MIN_LENGTHS.get('description', 50):
        return False, f"Description too short (min {MIN_LENGTHS['description']} chars)"
    
    if len(description) > MAX_LENGTHS.get('description', 50000):
        return False, f"Description too long (max {MAX_LENGTHS['description']} chars)"
    
    # Check for obvious garbage
    garbage_patterns = [
        r'^[\s\n\r]+$',  # Only whitespace
        r'^(loading|please wait|error)',  # Loading/error states
    ]
    
    desc_lower = description.lower().strip()
    for pattern in garbage_patterns:
        if re.match(pattern, desc_lower, re.IGNORECASE):
            return False, "Description appears to be garbage"
    
    return True, None


# ============================================================================
# JOB VALIDATION
# ============================================================================

def validate_job(job: Dict) -> Tuple[bool, List[str], List[str]]:
    """
    Validate a single job record.
    
    Args:
        job: Job dictionary to validate
        
    Returns:
        Tuple of (is_valid, errors, warnings)
    """
    errors = []
    warnings = []
    
    # Check required fields
    for field in REQUIRED_FIELDS:
        if not job.get(field):
            errors.append(f"Missing required field: {field}")
    
    # Validate URL
    if job.get('application_url'):
        is_valid, error = validate_url(job['application_url'])
        if not is_valid:
            errors.append(f"Invalid application_url: {error}")
    
    # Validate title
    if job.get('title'):
        is_valid, error = validate_title(job['title'])
        if not is_valid:
            warnings.append(f"Title validation: {error}")
    
    # Validate description
    if job.get('description'):
        is_valid, error = validate_description(job['description'])
        if not is_valid:
            warnings.append(f"Description validation: {error}")
    else:
        warnings.append("Missing description")
    
    # Check important fields
    for field in IMPORTANT_FIELDS:
        if field not in REQUIRED_FIELDS and not job.get(field):
            warnings.append(f"Missing important field: {field}")
    
    # Check for field completeness
    filled_fields = sum(1 for f in ALL_FIELDS if job.get(f))
    if filled_fields < 5:
        warnings.append(f"Low field completeness: only {filled_fields}/{len(ALL_FIELDS)} fields")
    
    is_valid = len(errors) == 0
    
    return is_valid, errors, warnings


def validate_jobs(jobs: List[Dict]) -> Tuple[List[Dict], List[Dict], Dict]:
    """
    Validate a list of jobs.
    
    Args:
        jobs: List of job dictionaries
        
    Returns:
        Tuple of (valid_jobs, invalid_jobs, stats)
    """
    valid_jobs = []
    invalid_jobs = []
    all_errors = []
    all_warnings = []
    
    for job in jobs:
        is_valid, errors, warnings = validate_job(job)
        
        all_errors.extend(errors)
        all_warnings.extend(warnings)
        
        if is_valid:
            valid_jobs.append(job)
        else:
            job['_validation_errors'] = errors
            job['_validation_warnings'] = warnings
            invalid_jobs.append(job)
    
    # Calculate stats
    stats = {
        'total_input': len(jobs),
        'valid': len(valid_jobs),
        'invalid': len(invalid_jobs),
        'validation_rate': len(valid_jobs) / len(jobs) if jobs else 0,
        'error_counts': {},
        'warning_counts': {},
    }
    
    # Count error types
    for error in all_errors:
        error_type = error.split(':')[0] if ':' in error else error
        stats['error_counts'][error_type] = stats['error_counts'].get(error_type, 0) + 1
    
    for warning in all_warnings:
        warning_type = warning.split(':')[0] if ':' in warning else warning
        stats['warning_counts'][warning_type] = stats['warning_counts'].get(warning_type, 0) + 1
    
    logger.info(f"Validation complete: {len(valid_jobs)}/{len(jobs)} jobs valid ({stats['validation_rate']:.1%})")
    
    return valid_jobs, invalid_jobs, stats


# ============================================================================
# QUALITY METRICS
# ============================================================================

def calculate_field_completeness(jobs: List[Dict]) -> Dict[str, float]:
    """
    Calculate field completeness rates.
    
    Args:
        jobs: List of job dictionaries
        
    Returns:
        Dictionary of field -> completeness rate
    """
    if not jobs:
        return {}
    
    completeness = {}
    
    for field in ALL_FIELDS:
        filled = sum(1 for job in jobs if job.get(field))
        completeness[field] = filled / len(jobs)
    
    return completeness


def calculate_quality_score(job: Dict) -> float:
    """
    Calculate a quality score for a single job.
    
    Score is based on:
    - Required field presence (40%)
    - Important field presence (30%)
    - Description quality (20%)
    - Metadata completeness (10%)
    
    Args:
        job: Job dictionary
        
    Returns:
        Quality score (0-100)
    """
    score = 0.0
    
    # Required fields (40%)
    required_filled = sum(1 for f in REQUIRED_FIELDS if job.get(f))
    score += (required_filled / len(REQUIRED_FIELDS)) * 40
    
    # Important fields (30%)
    important_filled = sum(1 for f in IMPORTANT_FIELDS if job.get(f))
    score += (important_filled / len(IMPORTANT_FIELDS)) * 30
    
    # Description quality (20%)
    desc = job.get('description', '')
    if desc:
        if len(desc) >= 500:
            score += 20
        elif len(desc) >= 200:
            score += 15
        elif len(desc) >= 50:
            score += 10
        else:
            score += 5
    
    # Metadata completeness (10%)
    metadata_fields = ['remote_type', 'employment_type', 'department', 
                       'experience_level', 'salary_range', 'date_posted']
    metadata_filled = sum(1 for f in metadata_fields if job.get(f))
    score += (metadata_filled / len(metadata_fields)) * 10
    
    return round(score, 1)


def calculate_batch_quality(jobs: List[Dict]) -> Dict:
    """
    Calculate overall quality metrics for a batch of jobs.
    
    Args:
        jobs: List of job dictionaries
        
    Returns:
        Quality metrics dictionary
    """
    if not jobs:
        return {'error': 'No jobs to analyze'}
    
    # Calculate individual scores
    scores = [calculate_quality_score(job) for job in jobs]
    
    # Field completeness
    completeness = calculate_field_completeness(jobs)
    
    # Score distribution
    score_ranges = {
        'excellent (90-100)': sum(1 for s in scores if s >= 90),
        'good (70-89)': sum(1 for s in scores if 70 <= s < 90),
        'fair (50-69)': sum(1 for s in scores if 50 <= s < 70),
        'poor (0-49)': sum(1 for s in scores if s < 50),
    }
    
    return {
        'total_jobs': len(jobs),
        'average_quality_score': round(sum(scores) / len(scores), 1),
        'min_score': min(scores),
        'max_score': max(scores),
        'score_distribution': score_ranges,
        'field_completeness': completeness,
        'field_completeness_summary': {
            'high (>80%)': sum(1 for c in completeness.values() if c > 0.8),
            'medium (50-80%)': sum(1 for c in completeness.values() if 0.5 <= c <= 0.8),
            'low (<50%)': sum(1 for c in completeness.values() if c < 0.5),
        },
    }


# ============================================================================
# DATA CLEANING
# ============================================================================

def clean_job_data(job: Dict) -> Dict:
    """
    Clean and normalize job data.
    
    Args:
        job: Job dictionary
        
    Returns:
        Cleaned job dictionary
    """
    cleaned = job.copy()
    
    # Strip whitespace from string fields
    for field in ALL_FIELDS:
        if field in cleaned and isinstance(cleaned[field], str):
            cleaned[field] = cleaned[field].strip()
            
            # Remove null-like strings
            if cleaned[field].lower() in ('null', 'undefined', 'none', 'n/a', ''):
                cleaned[field] = None
    
    # Normalize employment type
    emp_type = cleaned.get('employment_type', '')
    if emp_type:
        emp_type_lower = emp_type.lower()
        if 'full' in emp_type_lower and 'time' in emp_type_lower:
            cleaned['employment_type'] = 'Full-time'
        elif 'part' in emp_type_lower and 'time' in emp_type_lower:
            cleaned['employment_type'] = 'Part-time'
        elif 'contract' in emp_type_lower:
            cleaned['employment_type'] = 'Contract'
        elif 'intern' in emp_type_lower:
            cleaned['employment_type'] = 'Internship'
    
    # Normalize remote type
    remote = cleaned.get('remote_type', '')
    if remote:
        remote_lower = remote.lower()
        if 'remote' in remote_lower:
            cleaned['remote_type'] = 'Remote'
        elif 'hybrid' in remote_lower:
            cleaned['remote_type'] = 'Hybrid'
        elif 'on' in remote_lower and 'site' in remote_lower:
            cleaned['remote_type'] = 'Onsite'
    
    # Normalize experience level
    exp = cleaned.get('experience_level', '')
    if exp:
        exp_lower = exp.lower()
        if 'entry' in exp_lower or 'junior' in exp_lower:
            cleaned['experience_level'] = 'Entry'
        elif 'senior' in exp_lower or 'sr' in exp_lower:
            cleaned['experience_level'] = 'Senior'
        elif 'mid' in exp_lower or 'intermediate' in exp_lower:
            cleaned['experience_level'] = 'Mid'
        elif 'executive' in exp_lower or 'director' in exp_lower:
            cleaned['experience_level'] = 'Executive'
    
    return cleaned


def clean_jobs_batch(jobs: List[Dict]) -> List[Dict]:
    """
    Clean a batch of jobs.
    
    Args:
        jobs: List of job dictionaries
        
    Returns:
        List of cleaned job dictionaries
    """
    return [clean_job_data(job) for job in jobs]
