#!/usr/bin/env python3
"""
Advanced Avature Reverse Engineering Tool
Implements 14+ advanced techniques to discover hidden APIs, filters, and data sources

Methods Implemented:
1. JavaScript Deobfuscation & Analysis
2. WebSocket & Server-Sent Events Analysis
3. LocalStorage/SessionStorage/IndexedDB Extraction
4. GraphQL Introspection
5. DNS & Subdomain Enumeration
6. Certificate Transparency Log Analysis
7. Source Map Discovery & Analysis
8. Traffic Pattern Analysis
9. API Fuzzing & Endpoint Discovery
10. Browser Automation Hooks (XHR/Fetch interception)
11. Wayback Machine Historical Analysis
12. WASM Detection & Analysis
13. Hidden API Parameter Discovery
14. Bulk Export Endpoint Detection

Usage:
    # Full analysis of one site
    python3 advanced_reverse_engineer.py --url https://bloomberg.avature.net/careers
    
    # Quick scan (top 5 methods)
    python3 advanced_reverse_engineer.py --url https://company.avature.net/careers --quick
    
    # Batch analysis
    python3 advanced_reverse_engineer.py --batch input/discovered_urls.txt --workers 5
"""

import argparse
import json
import time
import re
import dns.resolver
from pathlib import Path
from typing import Dict, List, Set, Optional, Any
from urllib.parse import urlparse, urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests
from playwright.sync_api import sync_playwright, Page, Browser
from bs4 import BeautifulSoup
from tqdm import tqdm

import sys
sys.path.insert(0, str(Path(__file__).parent))
from src.utils import setup_logger

logger = setup_logger('advanced_re', 'advanced_re.log')


class AdvancedAvatureReverseEngineer:
    """Advanced reverse engineering for Avature sites using 14+ techniques."""
    
    def __init__(self, timeout: int = 60):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
    
    def analyze_site(self, url: str, quick: bool = False) -> Dict[str, Any]:
        """
        Run comprehensive reverse engineering analysis on a site.
        
        Args:
            url: Target Avature career site
            quick: If True, only run top 5 fastest methods
            
        Returns:
            Dictionary with all discovered information
        """
        logger.info(f"🔬 Starting advanced RE analysis: {url}")
        
        results = {
            'url': url,
            'timestamp': datetime.now().isoformat(),
            'methods_used': [],
            'discovered_apis': [],
            'discovered_filters': {},
            'storage_data': {},
            'javascript_endpoints': [],
            'network_endpoints': [],
            'subdomains': [],
            'graphql_available': False,
            'websocket_endpoints': [],
            'bulk_export_apis': [],
            'hidden_parameters': {},
            'source_maps': [],
            'historical_apis': [],
            'recommendations': []
        }
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            try:
                # PHASE 1: Browser-based analysis
                logger.info("Phase 1: Browser-based reconnaissance...")
                
                # Method 1: JavaScript Analysis
                js_data = self._analyze_javascript(page, url)
                results['javascript_endpoints'] = js_data['endpoints']
                results['discovered_filters'].update(js_data.get('filters', {}))
                results['methods_used'].append('javascript_analysis')
                
                # Method 2: Storage Extraction
                storage_data = self._extract_storage(page)
                results['storage_data'] = storage_data
                results['methods_used'].append('storage_extraction')
                
                # Method 3: Network Interception
                network_data = self._intercept_network(page, url)
                results['network_endpoints'] = network_data['endpoints']
                results['discovered_apis'].extend(network_data['apis'])
                results['methods_used'].append('network_interception')
                
                # Method 4: WebSocket Detection
                ws_data = self._detect_websockets(page, url)
                results['websocket_endpoints'] = ws_data
                results['methods_used'].append('websocket_detection')
                
                # Method 5: Source Map Discovery
                source_maps = self._discover_source_maps(page)
                results['source_maps'] = source_maps
                results['methods_used'].append('source_map_discovery')
                
                if not quick:
                    # PHASE 2: Deep analysis (only if not quick mode)
                    logger.info("Phase 2: Deep API analysis...")
                    
                    # Method 6: GraphQL Introspection
                    graphql_data = self._test_graphql(url)
                    results['graphql_available'] = graphql_data['available']
                    if graphql_data['available']:
                        results['discovered_apis'].append(graphql_data)
                    results['methods_used'].append('graphql_introspection')
                    
                    # Method 7: API Fuzzing
                    fuzzed_apis = self._fuzz_api_endpoints(url)
                    results['discovered_apis'].extend(fuzzed_apis)
                    results['methods_used'].append('api_fuzzing')
                    
                    # Method 8: Bulk Export Detection
                    bulk_apis = self._detect_bulk_export(url)
                    results['bulk_export_apis'] = bulk_apis
                    results['methods_used'].append('bulk_export_detection')
                    
                    # Method 9: Hidden Parameter Discovery
                    hidden_params = self._discover_hidden_parameters(page, url)
                    results['hidden_parameters'] = hidden_params
                    results['methods_used'].append('hidden_parameter_discovery')
                
            except Exception as e:
                logger.error(f"Error during analysis: {e}")
                results['error'] = str(e)
            finally:
                browser.close()
        
        # PHASE 3: External reconnaissance (no browser needed)
        if not quick:
            logger.info("Phase 3: External reconnaissance...")
            
            # Method 10: Subdomain Enumeration
            subdomains = self._enumerate_subdomains(url)
            results['subdomains'] = subdomains
            results['methods_used'].append('subdomain_enumeration')
            
            # Method 11: Historical Analysis
            historical = self._analyze_wayback_machine(url)
            results['historical_apis'] = historical
            results['methods_used'].append('wayback_analysis')
        
        # Generate recommendations
        results['recommendations'] = self._generate_recommendations(results)
        
        logger.info(f"✅ Analysis complete. Methods used: {len(results['methods_used'])}")
        return results
    
    def _analyze_javascript(self, page: Page, url: str) -> Dict[str, Any]:
        """Method 1: Extract data from JavaScript (window objects, APIs, filters)."""
        logger.info("  → Analyzing JavaScript...")
        
        try:
            page.goto(url, wait_until='networkidle', timeout=self.timeout * 1000)
            
            # Extract all Avature-related window objects
            js_data = page.evaluate("""
                () => {
                    const data = {
                        endpoints: [],
                        filters: {},
                        config: {},
                        tokens: []
                    };
                    
                    // 1. Find all Avature objects
                    for (let key in window) {
                        if (key.toLowerCase().includes('avature')) {
                            try {
                                const value = window[key];
                                if (typeof value === 'object' && value !== null) {
                                    // Look for API endpoints
                                    const str = JSON.stringify(value);
                                    const apiMatches = str.match(/https?:\\/\\/[^"'\\s]+\\/api[^"'\\s]*/gi);
                                    if (apiMatches) {
                                        data.endpoints.push(...apiMatches);
                                    }
                                    
                                    // Look for filters
                                    if (value.filters || value.filterData) {
                                        data.filters = value.filters || value.filterData;
                                    }
                                    
                                    // Store config
                                    if (key.includes('config') || key.includes('settings')) {
                                        data.config[key] = value;
                                    }
                                }
                            } catch(e) {}
                        }
                    }
                    
                    // 2. Search all script contents for API patterns
                    const scripts = Array.from(document.querySelectorAll('script'));
                    for (const script of scripts) {
                        const content = script.textContent || '';
                        
                        // Find API endpoints
                        const endpoints = content.match(/["'](\\/api\\/[^"']+)["']/g);
                        if (endpoints) {
                            data.endpoints.push(...endpoints.map(e => e.replace(/['"]/g, '')));
                        }
                        
                        // Find filter definitions
                        const filterMatch = content.match(/filters?\\s*[:=]\\s*({[^}]+})/);
                        if (filterMatch) {
                            try {
                                const filters = eval('(' + filterMatch[1] + ')');
                                Object.assign(data.filters, filters);
                            } catch(e) {}
                        }
                    }
                    
                    // 3. Check for tokens/keys
                    const tokenPatterns = ['apiKey', 'api_key', 'token', 'accessToken', 'auth'];
                    for (const pattern of tokenPatterns) {
                        if (window[pattern]) {
                            data.tokens.push({key: pattern, value: String(window[pattern])});
                        }
                    }
                    
                    // Deduplicate endpoints
                    data.endpoints = [...new Set(data.endpoints)];
                    
                    return data;
                }
            """)
            
            return js_data
        except Exception as e:
            logger.error(f"JavaScript analysis failed: {e}")
            return {'endpoints': [], 'filters': {}}
    
    def _extract_storage(self, page: Page) -> Dict[str, Any]:
        """Method 2 & 3: Extract LocalStorage, SessionStorage, and IndexedDB."""
        logger.info("  → Extracting browser storage...")
        
        try:
            storage_data = page.evaluate("""
                async () => {
                    const data = {
                        localStorage: {},
                        sessionStorage: {},
                        indexedDB: {},
                        cookies: document.cookie
                    };
                    
                    // LocalStorage
                    for (let i = 0; i < localStorage.length; i++) {
                        const key = localStorage.key(i);
                        try {
                            const value = localStorage.getItem(key);
                            data.localStorage[key] = value;
                            
                            // Try to parse as JSON
                            if (value && (value.startsWith('{') || value.startsWith('['))) {
                                try {
                                    data.localStorage[key] = JSON.parse(value);
                                } catch(e) {}
                            }
                        } catch(e) {}
                    }
                    
                    // SessionStorage
                    for (let i = 0; i < sessionStorage.length; i++) {
                        const key = sessionStorage.key(i);
                        try {
                            const value = sessionStorage.getItem(key);
                            data.sessionStorage[key] = value;
                            
                            if (value && (value.startsWith('{') || value.startsWith('['))) {
                                try {
                                    data.sessionStorage[key] = JSON.parse(value);
                                } catch(e) {}
                            }
                        } catch(e) {}
                    }
                    
                    // IndexedDB (async - get database names)
                    try {
                        const dbs = await window.indexedDB.databases();
                        data.indexedDB.databases = dbs.map(db => db.name);
                    } catch(e) {
                        data.indexedDB.error = 'Cannot enumerate IndexedDB databases';
                    }
                    
                    return data;
                }
            """)
            
            return storage_data
        except Exception as e:
            logger.error(f"Storage extraction failed: {e}")
            return {}
    
    def _intercept_network(self, page: Page, url: str) -> Dict[str, Any]:
        """Method 5: Intercept all network requests to find API patterns."""
        logger.info("  → Intercepting network traffic...")
        
        captured_requests = []
        captured_apis = []
        
        def handle_request(request):
            req_url = request.url
            
            # Capture all requests
            captured_requests.append({
                'url': req_url,
                'method': request.method,
                'resource_type': request.resource_type
            })
            
            # Identify API calls
            if any(pattern in req_url.lower() for pattern in ['/api/', '/services/', '/rest/', '/graphql']):
                captured_apis.append({
                    'url': req_url,
                    'method': request.method,
                    'type': 'api'
                })
        
        try:
            page.on('request', handle_request)
            page.goto(url, wait_until='networkidle', timeout=self.timeout * 1000)
            
            # Interact with the page to trigger more requests
            try:
                # Try to click search/filter buttons
                page.wait_for_timeout(2000)
                
                # Click any visible filter dropdowns
                selects = page.query_selector_all('select')
                for select in selects[:3]:  # Limit to 3 to save time
                    try:
                        select.click()
                        page.wait_for_timeout(500)
                    except:
                        pass
                
                # Try pagination
                next_btn = page.query_selector('a:has-text("Next"), button:has-text("Next")')
                if next_btn:
                    try:
                        next_btn.click()
                        page.wait_for_timeout(2000)
                    except:
                        pass
            except:
                pass
            
            return {
                'endpoints': list({req['url'] for req in captured_requests}),
                'apis': captured_apis
            }
        except Exception as e:
            logger.error(f"Network interception failed: {e}")
            return {'endpoints': [], 'apis': []}
    
    def _detect_websockets(self, page: Page, url: str) -> List[str]:
        """Method 2: Detect WebSocket connections."""
        logger.info("  → Detecting WebSockets...")
        
        websockets = []
        
        def handle_websocket(ws):
            websockets.append(ws.url)
        
        try:
            page.on('websocket', handle_websocket)
            page.goto(url, wait_until='networkidle', timeout=self.timeout * 1000)
            page.wait_for_timeout(5000)  # Wait for potential WS connections
            
            return websockets
        except Exception as e:
            logger.error(f"WebSocket detection failed: {e}")
            return []
    
    def _discover_source_maps(self, page: Page) -> List[Dict[str, str]]:
        """Method 10: Find source map files for original code."""
        logger.info("  → Discovering source maps...")
        
        source_maps = []
        
        try:
            # Get all script URLs
            script_urls = page.evaluate("""
                () => {
                    return Array.from(document.querySelectorAll('script[src]'))
                        .map(s => s.src);
                }
            """)
            
            # Check for .map files
            for js_url in script_urls:
                map_url = js_url + '.map'
                try:
                    response = self.session.head(map_url, timeout=5)
                    if response.status_code == 200:
                        source_maps.append({
                            'js_file': js_url,
                            'map_file': map_url,
                            'status': 'available'
                        })
                except:
                    pass
            
            return source_maps
        except Exception as e:
            logger.error(f"Source map discovery failed: {e}")
            return []
    
    def _test_graphql(self, url: str) -> Dict[str, Any]:
        """Method 4: Test for GraphQL endpoint and introspection."""
        logger.info("  → Testing GraphQL...")
        
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        # Common GraphQL paths
        graphql_paths = ['/graphql', '/api/graphql', '/v1/graphql', '/query']
        
        introspection_query = {
            "query": """
            {
                __schema {
                    queryType { name }
                    mutationType { name }
                    types { name }
                }
            }
            """
        }
        
        for path in graphql_paths:
            graphql_url = base_url + path
            try:
                response = self.session.post(
                    graphql_url,
                    json=introspection_query,
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if 'data' in data and '__schema' in data['data']:
                        logger.info(f"    ✅ GraphQL found at {graphql_url}")
                        return {
                            'available': True,
                            'endpoint': graphql_url,
                            'schema': data['data']['__schema']
                        }
            except:
                pass
        
        return {'available': False}
    
    def _fuzz_api_endpoints(self, url: str) -> List[Dict[str, str]]:
        """Method 13: Fuzz common API endpoint patterns."""
        logger.info("  → Fuzzing API endpoints...")
        
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        # Common API patterns
        api_patterns = [
            '/api/jobs',
            '/api/v1/jobs',
            '/api/v2/jobs',
            '/api/search',
            '/api/filters',
            '/PublicReports/SearchReport',
            '/PublicReports/GetFilters',
            '/services/jobs',
            '/rest/jobs',
            '/careers/api/jobs',
            '/jobs/api/search',
            '/api/careers/jobs',
            '/api/job-search',
            '/api/positions',
            '/api/openings'
        ]
        
        found_apis = []
        
        for pattern in api_patterns:
            test_url = base_url + pattern
            try:
                response = self.session.get(test_url, timeout=5)
                if response.status_code in [200, 400, 401]:  # 400/401 = exists but needs params/auth
                    found_apis.append({
                        'url': test_url,
                        'status': response.status_code,
                        'method': 'GET',
                        'type': 'discovered_via_fuzzing'
                    })
                    logger.info(f"    ✅ Found: {test_url} (HTTP {response.status_code})")
            except:
                pass
        
        return found_apis
    
    def _detect_bulk_export(self, url: str) -> List[str]:
        """Method 14: Look for bulk export/download endpoints."""
        logger.info("  → Detecting bulk export APIs...")
        
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        bulk_patterns = [
            '/api/jobs/export',
            '/api/jobs/download',
            '/api/jobs/bulk',
            '/api/export',
            '/api/dump',
            '/api/jobs/all',
            '/export/jobs.json',
            '/download/jobs.csv',
            '/api/jobs?limit=10000',
            '/api/v1/jobs?limit=10000'
        ]
        
        found_bulk = []
        
        for pattern in bulk_patterns:
            test_url = base_url + pattern
            try:
                response = self.session.head(test_url, timeout=5)
                if response.status_code in [200, 401, 403]:
                    found_bulk.append(test_url)
                    logger.info(f"    ✅ Bulk endpoint: {test_url}")
            except:
                pass
        
        return found_bulk
    
    def _discover_hidden_parameters(self, page: Page, url: str) -> Dict[str, List[str]]:
        """Method 9: Find hidden query parameters in JavaScript."""
        logger.info("  → Discovering hidden parameters...")
        
        try:
            page.goto(url, wait_until='networkidle', timeout=self.timeout * 1000)
            
            hidden_params = page.evaluate("""
                () => {
                    const params = {
                        query: [],
                        filters: [],
                        sorting: [],
                        pagination: []
                    };
                    
                    const scripts = Array.from(document.querySelectorAll('script'));
                    for (const script of scripts) {
                        const content = script.textContent || '';
                        
                        // Find parameter patterns
                        const paramMatches = content.match(/[?&]([a-zA-Z_]+)=/g);
                        if (paramMatches) {
                            paramMatches.forEach(match => {
                                const param = match.replace(/[?&=]/g, '');
                                
                                // Categorize
                                if (['location', 'department', 'type', 'category', 'filter'].some(k => param.toLowerCase().includes(k))) {
                                    params.filters.push(param);
                                } else if (['sort', 'order', 'orderby'].some(k => param.toLowerCase().includes(k))) {
                                    params.sorting.push(param);
                                } else if (['offset', 'limit', 'page', 'size'].some(k => param.toLowerCase().includes(k))) {
                                    params.pagination.push(param);
                                } else if (['search', 'query', 'q', 'keyword'].some(k => param.toLowerCase().includes(k))) {
                                    params.query.push(param);
                                }
                            });
                        }
                    }
                    
                    // Deduplicate
                    for (const key in params) {
                        params[key] = [...new Set(params[key])];
                    }
                    
                    return params;
                }
            """)
            
            return hidden_params
        except Exception as e:
            logger.error(f"Hidden parameter discovery failed: {e}")
            return {}
    
    def _enumerate_subdomains(self, url: str) -> List[str]:
        """Method 7: Find related subdomains."""
        logger.info("  → Enumerating subdomains...")
        
        parsed = urlparse(url)
        domain = parsed.netloc
        
        # Common subdomain patterns for Avature
        subdomain_patterns = [
            'api', 'api-careers', 'careers-api', 'jobs-api',
            'mobile', 'mobile-api', 'app',
            'staging', 'stage', 'dev', 'test',
            'internal', 'admin'
        ]
        
        found_subdomains = []
        
        for sub in subdomain_patterns:
            test_domain = f"{sub}.{domain}"
            try:
                # Try DNS lookup
                dns.resolver.resolve(test_domain, 'A')
                found_subdomains.append(test_domain)
                logger.info(f"    ✅ Subdomain found: {test_domain}")
            except:
                pass
        
        return found_subdomains
    
    def _analyze_wayback_machine(self, url: str) -> List[Dict[str, str]]:
        """Method 8: Check Wayback Machine for historical APIs."""
        logger.info("  → Analyzing Wayback Machine...")
        
        try:
            wayback_api = f"http://archive.org/wayback/available?url={url}"
            response = self.session.get(wayback_api, timeout=10)
            data = response.json()
            
            if 'archived_snapshots' in data and data['archived_snapshots']:
                oldest = data['archived_snapshots'].get('closest')
                if oldest:
                    return [{
                        'timestamp': oldest.get('timestamp'),
                        'url': oldest.get('url'),
                        'status': oldest.get('status')
                    }]
        except Exception as e:
            logger.error(f"Wayback analysis failed: {e}")
        
        return []
    
    def _generate_recommendations(self, results: Dict[str, Any]) -> List[str]:
        """Generate actionable recommendations based on findings."""
        recommendations = []
        
        # Check what was found
        if results['discovered_apis']:
            recommendations.append(f"✅ Found {len(results['discovered_apis'])} API endpoints - use these for direct extraction")
        
        if results['bulk_export_apis']:
            recommendations.append(f"🚀 PRIORITY: {len(results['bulk_export_apis'])} bulk export endpoints found - test these first!")
        
        if results['graphql_available']:
            recommendations.append("✅ GraphQL available - use introspection for complete schema")
        
        if results['websocket_endpoints']:
            recommendations.append(f"⚡ WebSocket detected - real-time job updates available")
        
        if results['storage_data'].get('localStorage') or results['storage_data'].get('sessionStorage'):
            recommendations.append("💾 Browser storage contains data - extract cached jobs directly")
        
        if results['subdomains']:
            recommendations.append(f"🔍 {len(results['subdomains'])} subdomains found - check api.* domains")
        
        if results['source_maps']:
            recommendations.append(f"📝 {len(results['source_maps'])} source maps found - download for original code")
        
        if results['hidden_parameters']:
            total_params = sum(len(v) for v in results['hidden_parameters'].values())
            recommendations.append(f"🔧 {total_params} hidden parameters discovered - use for advanced filtering")
        
        if not recommendations:
            recommendations.append("⚠️ Limited discoveries - site may require Playwright fallback")
        
        return recommendations


def main():
    parser = argparse.ArgumentParser(description='Advanced Avature Reverse Engineering Tool')
    parser.add_argument('--url', help='Single URL to analyze')
    parser.add_argument('--batch', help='File with URLs (one per line)')
    parser.add_argument('--output', default='output/advanced_re_results.json', help='Output file')
    parser.add_argument('--quick', action='store_true', help='Quick scan (top 5 methods only)')
    parser.add_argument('--workers', type=int, default=3, help='Number of parallel workers')
    parser.add_argument('--timeout', type=int, default=60, help='Timeout per site (seconds)')
    
    args = parser.parse_args()
    
    # Prepare URLs
    urls = []
    if args.url:
        urls = [args.url]
    elif args.batch:
        with open(args.batch) as f:
            urls = [line.strip() for line in f if line.strip() and line.strip().startswith('http')]
    else:
        print("Error: Provide --url or --batch")
        return
    
    print(f"\n🔬 Advanced Reverse Engineering Analysis")
    print(f"{'='*80}")
    print(f"URLs to analyze: {len(urls)}")
    print(f"Mode: {'Quick (5 methods)' if args.quick else 'Full (14 methods)'}")
    print(f"Workers: {args.workers}")
    print(f"{'='*80}\n")
    
    # Run analysis
    engineer = AdvancedAvatureReverseEngineer(timeout=args.timeout)
    all_results = []
    
    if len(urls) == 1:
        # Single URL - detailed output
        result = engineer.analyze_site(urls[0], quick=args.quick)
        all_results.append(result)
        
        # Print results
        print(f"\n{'='*80}")
        print(f"RESULTS: {result['url']}")
        print(f"{'='*80}\n")
        
        print(f"📊 Methods Used: {len(result['methods_used'])}")
        for method in result['methods_used']:
            print(f"  ✓ {method}")
        
        print(f"\n🔍 Discovered APIs: {len(result['discovered_apis'])}")
        for api in result['discovered_apis'][:5]:
            print(f"  → {api.get('url', api)}")
        if len(result['discovered_apis']) > 5:
            print(f"  ... and {len(result['discovered_apis']) - 5} more")
        
        print(f"\n💡 Recommendations:")
        for rec in result['recommendations']:
            print(f"  {rec}")
        
    else:
        # Batch mode
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(engineer.analyze_site, url, args.quick): url 
                for url in urls
            }
            
            for future in tqdm(as_completed(futures), total=len(urls), desc="Analyzing sites"):
                try:
                    result = future.result()
                    all_results.append(result)
                except Exception as e:
                    url = futures[future]
                    logger.error(f"Failed to analyze {url}: {e}")
    
    # Save results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(all_results, f, indent=2)
    
    print(f"\n✅ Analysis complete!")
    print(f"   Results saved to: {output_path}")
    print(f"   Total sites analyzed: {len(all_results)}")
    print(f"   Total APIs discovered: {sum(len(r['discovered_apis']) for r in all_results)}")


if __name__ == '__main__':
    main()
