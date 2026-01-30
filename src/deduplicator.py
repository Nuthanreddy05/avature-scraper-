"""
Deduplication Module for Avature Scraper.

Uses SHA-256 content hashing to identify and remove duplicate jobs.
Catches reposts with different dates but same content.

Expected deduplication rate: 10-15%
"""

import hashlib
from typing import Dict, List, Set, Tuple
from collections import defaultdict

from .utils import setup_logger


logger = setup_logger('deduplicator')


# ============================================================================
# HASH GENERATION
# ============================================================================

def generate_content_hash(job: Dict) -> str:
    """
    Generate SHA-256 hash from job content.
    
    Uses title + description + location for hash.
    Excludes date (same job reposted = same content).
    
    Args:
        job: Job data dictionary
        
    Returns:
        SHA-256 hash string
    """
    # Normalize fields for consistent hashing
    title = (job.get('title') or '').strip().lower()
    description = (job.get('description') or '').strip().lower()
    location = (job.get('location') or '').strip().lower()
    
    # Create content string
    content = f"{title}|{description}|{location}"
    
    # Generate hash
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def generate_title_hash(job: Dict) -> str:
    """
    Generate a simpler hash based on title only.
    
    Useful for detecting near-duplicates where descriptions
    have minor variations.
    
    Args:
        job: Job data dictionary
        
    Returns:
        SHA-256 hash of normalized title
    """
    title = (job.get('title') or '').strip().lower()
    company = (job.get('company_name') or '').strip().lower()
    
    content = f"{company}|{title}"
    
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def generate_url_hash(job: Dict) -> str:
    """
    Generate hash from job URL.
    
    Catches exact duplicates scraped multiple times.
    
    Args:
        job: Job data dictionary
        
    Returns:
        SHA-256 hash of URL
    """
    url = (job.get('application_url') or '').strip().lower()
    
    return hashlib.sha256(url.encode('utf-8')).hexdigest()


# ============================================================================
# DEDUPLICATION FUNCTIONS
# ============================================================================

def deduplicate_jobs(
    jobs: List[Dict],
    strategy: str = 'content'
) -> Tuple[List[Dict], Dict]:
    """
    Remove duplicate jobs using specified strategy.
    
    Strategies:
    - 'content': Hash of title + description + location
    - 'title': Hash of company + title only
    - 'url': Hash of URL only
    - 'hybrid': Combines multiple strategies
    
    Args:
        jobs: List of job dictionaries
        strategy: Deduplication strategy
        
    Returns:
        Tuple of (unique_jobs, stats)
    """
    if not jobs:
        return [], {'total_input': 0, 'total_output': 0, 'duplicates_removed': 0}
    
    logger.info(f"Deduplicating {len(jobs)} jobs using '{strategy}' strategy...")
    
    if strategy == 'content':
        unique_jobs, stats = _dedupe_by_content(jobs)
    elif strategy == 'title':
        unique_jobs, stats = _dedupe_by_title(jobs)
    elif strategy == 'url':
        unique_jobs, stats = _dedupe_by_url(jobs)
    elif strategy == 'hybrid':
        unique_jobs, stats = _dedupe_hybrid(jobs)
    else:
        logger.warning(f"Unknown strategy '{strategy}', using 'content'")
        unique_jobs, stats = _dedupe_by_content(jobs)
    
    dedup_rate = stats['duplicates_removed'] / stats['total_input'] if stats['total_input'] > 0 else 0
    logger.info(f"Deduplication complete: {stats['total_input']} → {stats['total_output']} ({dedup_rate:.1%} removed)")
    
    return unique_jobs, stats


def _dedupe_by_content(jobs: List[Dict]) -> Tuple[List[Dict], Dict]:
    """Deduplicate by content hash."""
    seen_hashes: Set[str] = set()
    unique_jobs: List[Dict] = []
    duplicate_count = 0
    
    for job in jobs:
        content_hash = generate_content_hash(job)
        
        if content_hash not in seen_hashes:
            seen_hashes.add(content_hash)
            job['content_hash'] = content_hash
            unique_jobs.append(job)
        else:
            duplicate_count += 1
    
    return unique_jobs, {
        'total_input': len(jobs),
        'total_output': len(unique_jobs),
        'duplicates_removed': duplicate_count,
        'strategy': 'content',
    }


def _dedupe_by_title(jobs: List[Dict]) -> Tuple[List[Dict], Dict]:
    """Deduplicate by title hash."""
    seen_hashes: Set[str] = set()
    unique_jobs: List[Dict] = []
    duplicate_count = 0
    
    for job in jobs:
        title_hash = generate_title_hash(job)
        
        if title_hash not in seen_hashes:
            seen_hashes.add(title_hash)
            job['title_hash'] = title_hash
            unique_jobs.append(job)
        else:
            duplicate_count += 1
    
    return unique_jobs, {
        'total_input': len(jobs),
        'total_output': len(unique_jobs),
        'duplicates_removed': duplicate_count,
        'strategy': 'title',
    }


def _dedupe_by_url(jobs: List[Dict]) -> Tuple[List[Dict], Dict]:
    """Deduplicate by URL hash."""
    seen_hashes: Set[str] = set()
    unique_jobs: List[Dict] = []
    duplicate_count = 0
    
    for job in jobs:
        url_hash = generate_url_hash(job)
        
        if url_hash not in seen_hashes:
            seen_hashes.add(url_hash)
            job['url_hash'] = url_hash
            unique_jobs.append(job)
        else:
            duplicate_count += 1
    
    return unique_jobs, {
        'total_input': len(jobs),
        'total_output': len(unique_jobs),
        'duplicates_removed': duplicate_count,
        'strategy': 'url',
    }


def _dedupe_hybrid(jobs: List[Dict]) -> Tuple[List[Dict], Dict]:
    """
    Hybrid deduplication combining multiple strategies.
    
    Uses a tiered approach:
    1. First, remove exact URL duplicates
    2. Then, remove content duplicates
    3. Finally, flag title duplicates but keep them
    """
    # Step 1: URL deduplication
    url_hashes: Set[str] = set()
    after_url: List[Dict] = []
    url_dupes = 0
    
    for job in jobs:
        url_hash = generate_url_hash(job)
        if url_hash not in url_hashes:
            url_hashes.add(url_hash)
            job['url_hash'] = url_hash
            after_url.append(job)
        else:
            url_dupes += 1
    
    # Step 2: Content deduplication
    content_hashes: Set[str] = set()
    after_content: List[Dict] = []
    content_dupes = 0
    
    for job in after_url:
        content_hash = generate_content_hash(job)
        if content_hash not in content_hashes:
            content_hashes.add(content_hash)
            job['content_hash'] = content_hash
            after_content.append(job)
        else:
            content_dupes += 1
    
    # Step 3: Flag title duplicates (keep but mark)
    title_counts: Dict[str, int] = defaultdict(int)
    for job in after_content:
        title_hash = generate_title_hash(job)
        title_counts[title_hash] += 1
        job['title_hash'] = title_hash
    
    # Mark jobs that have title duplicates
    for job in after_content:
        if title_counts[job['title_hash']] > 1:
            job['has_title_duplicate'] = True
    
    return after_content, {
        'total_input': len(jobs),
        'total_output': len(after_content),
        'duplicates_removed': url_dupes + content_dupes,
        'url_duplicates': url_dupes,
        'content_duplicates': content_dupes,
        'title_duplicates_flagged': sum(1 for c in title_counts.values() if c > 1),
        'strategy': 'hybrid',
    }


# ============================================================================
# ANALYSIS FUNCTIONS
# ============================================================================

def analyze_duplicates(jobs: List[Dict]) -> Dict:
    """
    Analyze duplicate patterns in job data.
    
    Useful for understanding data quality and duplicate sources.
    
    Args:
        jobs: List of job dictionaries
        
    Returns:
        Analysis results
    """
    if not jobs:
        return {'error': 'No jobs to analyze'}
    
    # Track hashes
    url_hashes: Dict[str, List[int]] = defaultdict(list)
    content_hashes: Dict[str, List[int]] = defaultdict(list)
    title_hashes: Dict[str, List[int]] = defaultdict(list)
    
    for i, job in enumerate(jobs):
        url_hashes[generate_url_hash(job)].append(i)
        content_hashes[generate_content_hash(job)].append(i)
        title_hashes[generate_title_hash(job)].append(i)
    
    # Find duplicates
    url_dupes = {h: indices for h, indices in url_hashes.items() if len(indices) > 1}
    content_dupes = {h: indices for h, indices in content_hashes.items() if len(indices) > 1}
    title_dupes = {h: indices for h, indices in title_hashes.items() if len(indices) > 1}
    
    # Analyze by company
    company_dupes: Dict[str, int] = defaultdict(int)
    for indices in content_dupes.values():
        company = jobs[indices[0]].get('company_name', 'Unknown')
        company_dupes[company] += len(indices) - 1
    
    return {
        'total_jobs': len(jobs),
        'url_duplicates': {
            'count': len(url_dupes),
            'total_affected': sum(len(i) for i in url_dupes.values()),
        },
        'content_duplicates': {
            'count': len(content_dupes),
            'total_affected': sum(len(i) for i in content_dupes.values()),
        },
        'title_duplicates': {
            'count': len(title_dupes),
            'total_affected': sum(len(i) for i in title_dupes.values()),
        },
        'duplicates_by_company': dict(sorted(
            company_dupes.items(),
            key=lambda x: -x[1]
        )[:20]),
    }


def find_similar_jobs(
    jobs: List[Dict],
    threshold: float = 0.8
) -> List[Tuple[int, int, float]]:
    """
    Find similar (but not identical) jobs.
    
    Uses simple text similarity for detection.
    
    Args:
        jobs: List of job dictionaries
        threshold: Similarity threshold (0-1)
        
    Returns:
        List of (index1, index2, similarity) tuples
    """
    similar_pairs = []
    
    # Simple word-based similarity
    def get_words(text: str) -> Set[str]:
        return set((text or '').lower().split())
    
    def jaccard_similarity(set1: Set[str], set2: Set[str]) -> float:
        if not set1 or not set2:
            return 0.0
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0.0
    
    # Pre-compute word sets
    word_sets = [get_words(job.get('title', '')) for job in jobs]
    
    # Compare pairs (this is O(n^2) - for large datasets, use LSH)
    n = min(len(jobs), 1000)  # Limit for performance
    for i in range(n):
        for j in range(i + 1, n):
            similarity = jaccard_similarity(word_sets[i], word_sets[j])
            if similarity >= threshold and similarity < 1.0:
                similar_pairs.append((i, j, similarity))
    
    return sorted(similar_pairs, key=lambda x: -x[2])[:100]
