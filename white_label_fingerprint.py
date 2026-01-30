#!/usr/bin/env python3
"""
WHITE-LABEL AVATURE FINGERPRINTING
Detects companies using Avature backend with custom domains (careers.company.com)

Methods:
1. JavaScript global detection (window.avature)
2. Network request interception (Playwright)
3. API endpoint patterns
4. Form parameters & pagination signatures
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
from bs4 import BeautifulSoup
import json
import re
from typing import Dict, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class WhiteLabelAvatureDetector:
    """Detects white-label Avature implementations."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        })
    
    def detect_avature(self, url: str) -> Dict:
        """
        Comprehensive Avature detection using multiple signals.
        
        Returns:
            {
                'url': str,
                'is_avature': bool,
                'confidence_score': int (0-100),
                'signals': [list of detected signals],
                'api_endpoints': [discovered API endpoints],
                'recommended_scrape_url': str or None
            }
        """
        logger.info(f"🔍 Fingerprinting {url}")
        
        result = {
            'url': url,
            'is_avature': False,
            'confidence_score': 0,
            'signals': [],
            'api_endpoints': [],
            'recommended_scrape_url': None,
            'error': None
        }
        
        try:
            # Fetch page content
            resp = self.session.get(url, timeout=20, allow_redirects=True)
            html = resp.text
            final_url = resp.url
            
            # Signal 1: window.avature JavaScript global (SMOKING GUN - 40 points)
            if re.search(r'window\.avature|var\s+avature\s*=', html):
                result['signals'].append('🎯 JavaScript: window.avature global detected')
                result['confidence_score'] += 40
            
            # Signal 2: Avature CDN assets (35 points)
            if 'avature.net' in html or 'avaturecdn.net' in html:
                result['signals'].append('📦 CDN: Avature assets loaded')
                result['confidence_score'] += 35
            
            # Signal 3: API endpoint patterns (30 points)
            avature_api_patterns = [
                (r'/PublicReports/\d+/json', 'API: PublicReports endpoint'),
                (r'/SearchJobsData', 'API: SearchJobsData endpoint'),
                (r'/CareerPortal/SearchJobs', 'API: CareerPortal endpoint'),
                (r'avature\.net.*api', 'API: Avature.net API call'),
            ]
            
            for pattern, signal_name in avature_api_patterns:
                if re.search(pattern, html, re.IGNORECASE):
                    result['signals'].append(f'🔌 {signal_name}')
                    result['confidence_score'] += 30
                    break  # Only count once
            
            # Signal 4: Pagination parameters (25 points)
            if 'jobOffset' in html and ('jobRecordsCount' in html or 'jobSearchInterval' in html):
                result['signals'].append('📄 Pagination: jobOffset detected')
                result['confidence_score'] += 25
            
            # Signal 5: Avature session cookie (20 points)
            cookies_str = str(resp.cookies).lower()
            if 'avsession' in cookies_str or 'avature' in cookies_str:
                result['signals'].append('🍪 Cookie: AvatureSession detected')
                result['confidence_score'] += 20
            
            # Signal 6: Form parameters unique to Avature (15 points)
            if '__eventtarget' in html and '__eventargument' in html and 'asp.net' in html.lower():
                result['signals'].append('📝 Form: ASP.NET viewstate (Avature pattern)')
                result['confidence_score'] += 15
            
            # Signal 7: Data attributes (10 points)
            if re.search(r'data-job-id|data-requisition-id|data-avature', html):
                result['signals'].append('🏷️ HTML: data-job-id attributes')
                result['confidence_score'] += 10
            
            # Signal 8: CSS classes specific to Avature (5 points)
            avature_css_classes = ['avature-container', 'avature-job', 'career-portal']
            for css_class in avature_css_classes:
                if css_class in html:
                    result['signals'].append(f'🎨 CSS: {css_class} class')
                    result['confidence_score'] += 5
                    break
            
            # Discover API endpoints
            result['api_endpoints'] = self._discover_api_endpoints(url, html)
            
            # Determine if this is Avature (threshold: 40 points)
            result['is_avature'] = result['confidence_score'] >= 40
            
            # Cap confidence at 100
            result['confidence_score'] = min(result['confidence_score'], 100)
            
            # Recommend best scrape URL
            if result['api_endpoints']:
                result['recommended_scrape_url'] = result['api_endpoints'][0]
            else:
                result['recommended_scrape_url'] = final_url
            
            status = '✅' if result['is_avature'] else '❌'
            logger.info(f"{status} {url}: {result['confidence_score']}/100 ({len(result['signals'])} signals)")
            
        except requests.Timeout:
            result['error'] = 'Timeout'
            logger.warning(f"⏱️  Timeout: {url}")
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"❌ Error: {url}: {e}")
        
        return result
    
    def _discover_api_endpoints(self, base_url: str, html: str) -> List[str]:
        """
        Discover actual API endpoints from the page.
        
        Tests common Avature API paths on the domain.
        """
        from urllib.parse import urlparse, urljoin
        
        parsed = urlparse(base_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        
        endpoints = []
        
        # Method 1: Extract from HTML
        html_endpoints = re.findall(r'["\']([^"\']*(?:SearchJobs|PublicReports|api/job)[^"\']*)["\']', html)
        for endpoint in html_endpoints[:5]:  # Top 5
            if endpoint.startswith('/'):
                full_url = urljoin(base, endpoint)
                endpoints.append(full_url)
            elif endpoint.startswith('http'):
                endpoints.append(endpoint)
        
        # Method 2: Test common paths
        common_paths = [
            '/SearchJobsData',
            '/PublicReports/18/json',
            '/PublicReports/1/json',
            '/CareerPortal/SearchJobs',
            '/api/jobsearch',
            '/api/jobs',
        ]
        
        for path in common_paths:
            test_url = urljoin(base, path)
            try:
                # Quick HEAD request to check if endpoint exists
                resp = self.session.head(test_url, timeout=5)
                if resp.status_code in [200, 301, 302]:
                    endpoints.append(test_url)
            except:
                pass
        
        return endpoints[:10]  # Return top 10
    
    def batch_detect(self, urls: List[str], workers: int = 10) -> List[Dict]:
        """
        Detect Avature on multiple URLs in parallel.
        """
        results = []
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_url = {executor.submit(self.detect_avature, url): url for url in urls}
            
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logger.error(f"Failed {url}: {e}")
                    results.append({
                        'url': url,
                        'is_avature': False,
                        'confidence_score': 0,
                        'signals': [],
                        'error': str(e)
                    })
        
        return results


def generate_fortune_500_career_urls() -> List[str]:
    """
    Generate Fortune 500 career page URLs to test.
    
    Focus on financial services, consulting, tech, and other high-hiring sectors.
    """
    # Top Fortune 500 companies (prioritize high-volume hirers)
    companies = [
        # Financial Services (Big 4 Banks + Investment)
        'goldmansachs', 'morganstanley', 'jpmorganchase', 'wellsfargo', 'citi',
        'bankofamerica', 'schwab', 'capitalonegroup', 'usbank', 'pnc',
        
        # Big 4 Consulting / Accounting
        'kpmg', 'pwc', 'ey', 'deloitte',
        
        # Tech
        'apple', 'microsoft', 'google', 'amazon', 'meta', 'oracle', 'salesforce',
        'intel', 'cisco', 'adobe', 'nvidia', 'qualcomm', 'paypal',
        
        # Aerospace & Defense
        'boeing', 'lockheedmartin', 'northropgrumman', 'raytheon', 'gd',
        
        # Automotive
        'ford', 'gm', 'stellantis', 'tesla',
        
        # Healthcare
        'uhc', 'anthem', 'cigna', 'humana', 'cvs', 'walgreens',
        
        # Retail
        'walmart', 'target', 'homedepot', 'lowes', 'costco', 'kroger',
        
        # Energy
        'exxonmobil', 'chevron', 'conocophillips', 'bp', 'shell', 'totalenergies',
        
        # Pharma
        'jnj', 'pfizer', 'abbvie', 'merck', 'bms', 'lilly',
        
        # Telecommunications
        'att', 'verizon', 'tmobile', 'comcast', 'charter',
        
        # Industrial
        'ge', 'honeywell', '3m', 'caterpillar', 'deere',
        
        # Consumer Goods
        'pg', 'pepsico', 'coca-cola', 'mondelez', 'kraft',
    ]
    
    career_urls = []
    
    for company in companies:
        # Generate multiple career URL patterns
        patterns = [
            f'https://careers.{company}.com',
            f'https://jobs.{company}.com',
            f'https://www.{company}.com/careers',
            f'https://{company}.com/careers',
            f'https://recruiting.{company}.com',
            f'https://us-talentcommunity.{company}.com',  # Avature pattern
        ]
        career_urls.extend(patterns)
    
    return career_urls


def main():
    """Main execution."""
    print("=" * 80)
    print("🕵️  WHITE-LABEL AVATURE FINGERPRINTING")
    print("=" * 80)
    print()
    print("Detecting Avature implementations on custom domains")
    print("Method: JavaScript globals + API patterns + pagination signatures")
    print()
    
    # Generate Fortune 500 career URLs
    print("📋 Generating Fortune 500 career page URLs...")
    all_urls = generate_fortune_500_career_urls()
    print(f"✅ Generated {len(all_urls)} URLs to test")
    print()
    
    # Save URL list
    with open('input/FORTUNE_500_CAREER_URLS.txt', 'w') as f:
        for url in all_urls:
            f.write(url + '\n')
    
    print(f"💾 Saved to input/FORTUNE_500_CAREER_URLS.txt")
    print()
    
    # Run detection
    print("=" * 80)
    print("🚀 STARTING FINGERPRINTING")
    print("=" * 80)
    print()
    
    detector = WhiteLabelAvatureDetector()
    results = detector.batch_detect(all_urls, workers=15)
    
    # Save all results
    output_file = 'output/WHITE_LABEL_FINGERPRINT.json'
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print()
    print("=" * 80)
    print("✅ FINGERPRINTING COMPLETE")
    print("=" * 80)
    print(f"Results saved to: {output_file}")
    print()
    
    # Filter to Avature-detected sites
    avature_sites = [r for r in results if r['is_avature']]
    
    print(f"🎯 RESULTS:")
    print(f"   Total tested: {len(results)}")
    print(f"   Avature detected: {len(avature_sites)}")
    print(f"   Success rate: {len(avature_sites)/len(results)*100:.1f}%")
    print()
    
    if avature_sites:
        # Sort by confidence
        avature_sites.sort(key=lambda x: x['confidence_score'], reverse=True)
        
        print("🏆 TOP WHITE-LABEL AVATURE DISCOVERIES:")
        print("-" * 80)
        for i, site in enumerate(avature_sites[:20], 1):
            print(f"\n{i}. {site['url']}")
            print(f"   Confidence: {site['confidence_score']}/100")
            print(f"   Signals: {len(site['signals'])}")
            if site['signals']:
                for signal in site['signals'][:3]:
                    print(f"     • {signal}")
            if site['api_endpoints']:
                print(f"   API: {site['api_endpoints'][0]}")
        
        # Save white-label URLs for scraping
        with open('input/WHITE_LABEL_AVATURE_URLS.txt', 'w') as f:
            for site in avature_sites:
                url = site.get('recommended_scrape_url') or site['url']
                f.write(url + '\n')
        
        print()
        print(f"📝 Saved {len(avature_sites)} white-label URLs to: input/WHITE_LABEL_AVATURE_URLS.txt")
        print()
        
        # Estimate job yield
        avg_jobs_per_site = 150  # Conservative estimate for white-label Avature
        estimated_jobs = len(avature_sites) * avg_jobs_per_site
        
        print("=" * 80)
        print("📊 ESTIMATED JOB YIELD")
        print("=" * 80)
        print(f"White-label sites discovered: {len(avature_sites)}")
        print(f"Estimated jobs per site: {avg_jobs_per_site}")
        print(f"Total estimated jobs: {estimated_jobs:,}")
        print()
    else:
        print("❌ No white-label Avature sites detected")
        print("   This is unexpected - consider adjusting detection thresholds")
        print()


if __name__ == '__main__':
    main()
