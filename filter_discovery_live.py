#!/usr/bin/env python3
"""
LIVE FILTER DISCOVERY - Playwright-based
Discovers dynamically loaded filters on confirmed Avature sites
"""

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import json
import re
from typing import Dict, List
import time

def discover_avature_filters_live(url: str) -> Dict:
    """
    Use Playwright to capture dynamically loaded Avature filters.
    
    Returns:
        {
            'url': str,
            'filters': {
                'location': [{'value': 'NY', 'text': 'New York'}, ...],
                'department': [...],
                ...
            },
            'javascript_data': {...},
            'total_jobs_visible': int
        }
    """
    result = {
        'url': url,
        'filters': {},
        'javascript_data': None,
        'total_jobs_visible': 0,
        'error': None
    }
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        page = context.new_page()
        
        try:
            print(f"  🌐 Loading {url}...")
            page.goto(url, wait_until='networkidle', timeout=45000)
            
            # Wait for filters to render
            page.wait_for_timeout(4000)
            
            print(f"  🔍 Extracting filters...")
            
            # Method 1: Extract from window.avature JavaScript object
            avature_data = page.evaluate('''() => {
                try {
                    if (window.avature) {
                        return {
                            filters: window.avature.filters || null,
                            searchCriteria: window.avature.searchCriteria || null,
                            facets: window.avature.facets || null,
                            config: window.avature.config || null
                        };
                    }
                    return null;
                } catch (e) {
                    return null;
                }
            }''')
            
            if avature_data:
                result['javascript_data'] = avature_data
                print(f"    ✅ Found window.avature data")
            
            # Method 2: Extract from HTML select elements
            selects = page.query_selector_all('select')
            for select in selects:
                try:
                    name = (
                        select.get_attribute('name') or 
                        select.get_attribute('id') or 
                        select.get_attribute('data-filter') or
                        ''
                    )
                    
                    # Clean up name
                    name = name.replace('filter', '').replace('_', '').strip()
                    
                    if not name or name in ['search', 'sort', 'pagesize', 'page']:
                        continue
                    
                    # Get options
                    options = []
                    option_els = select.query_selector_all('option')
                    for opt in option_els:
                        value = opt.get_attribute('value')
                        text = opt.inner_text().strip()
                        
                        if value and value not in ['', 'all', '*', '-1', 'null'] and text:
                            options.append({'value': value, 'text': text})
                    
                    if options:
                        result['filters'][name] = options
                        print(f"    📋 {name}: {len(options)} options")
                        
                except Exception as e:
                    pass
            
            # Method 3: Look for Avature-specific filter containers
            filter_containers = page.query_selector_all('[data-filter], [data-facet], .filter-group, .facet-group')
            for container in filter_containers:
                try:
                    # Get filter name from label or data attribute
                    filter_name = (
                        container.get_attribute('data-filter') or
                        container.get_attribute('data-facet')
                    )
                    
                    if not filter_name:
                        label = container.query_selector('label, .filter-label, legend')
                        if label:
                            filter_name = label.inner_text().strip().lower().replace(' ', '_')
                    
                    if filter_name and filter_name not in result['filters']:
                        # Extract options from checkboxes/radios
                        inputs = container.query_selector_all('input[type="checkbox"], input[type="radio"]')
                        options = []
                        
                        for inp in inputs:
                            value = inp.get_attribute('value')
                            label_el = inp.evaluate('el => el.nextElementSibling || el.parentElement')
                            text = label_el.inner_text().strip() if hasattr(label_el, 'inner_text') else value
                            
                            if value and value not in ['', 'all']:
                                options.append({'value': value, 'text': text})
                        
                        if options:
                            result['filters'][filter_name] = options
                            print(f"    📋 {filter_name}: {len(options)} options (checkboxes)")
                            
                except Exception as e:
                    pass
            
            # Method 4: Extract total job count
            try:
                body_text = page.inner_text('body')
                patterns = [
                    r'(\d+)\s+(?:jobs?|positions?|openings?)',
                    r'showing\s+\d+\s+of\s+(\d+)',
                    r'(\d+)\s+results?',
                    r'total.*?(\d+)',
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, body_text, re.IGNORECASE)
                    if match:
                        count = int(match.group(1))
                        if count > 0 and count < 100000:  # Sanity check
                            result['total_jobs_visible'] = count
                            print(f"    📊 Total jobs visible: {count}")
                            break
            except:
                pass
            
        except PlaywrightTimeout:
            result['error'] = 'Timeout'
            print(f"  ⏱️  Timeout loading {url}")
        except Exception as e:
            result['error'] = str(e)
            print(f"  ❌ Error: {e}")
        finally:
            browser.close()
    
    return result


def main():
    """Run filter discovery on confirmed Avature sites."""
    print("=" * 80)
    print("🔍 LIVE FILTER DISCOVERY (Confirmed Avature Sites)")
    print("=" * 80)
    print()
    
    # Load confirmed Avature URLs
    with open('input/CONFIRMED_AVATURE.txt') as f:
        sites = [line.strip() for line in f if line.strip()]
    
    print(f"Targets: {len(sites)} confirmed Avature sites")
    print()
    
    all_results = []
    
    for i, site in enumerate(sites, 1):
        print(f"\n[{i}/{len(sites)}] {site}")
        result = discover_avature_filters_live(site)
        all_results.append(result)
        
        time.sleep(2)  # Rate limit
    
    # Save results
    output_file = 'output/FILTER_DISCOVERIES_LIVE.json'
    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2)
    
    print()
    print("=" * 80)
    print("✅ FILTER DISCOVERY COMPLETE")
    print("=" * 80)
    print(f"Results saved to: {output_file}")
    print()
    
    # Summary
    total_filters = sum(len(r['filters']) for r in all_results)
    total_jobs = sum(r['total_jobs_visible'] for r in all_results)
    sites_with_filters = sum(1 for r in all_results if r['filters'])
    
    print(f"📊 SUMMARY:")
    print(f"   Sites with filters: {sites_with_filters}/{len(sites)}")
    print(f"   Total filter types discovered: {total_filters}")
    print(f"   Total jobs visible: {total_jobs:,}")
    print()
    
    # Show top discoveries
    print("🏆 TOP FILTER DISCOVERIES:")
    sorted_results = sorted(all_results, key=lambda x: len(x['filters']), reverse=True)
    for r in sorted_results[:5]:
        if r['filters']:
            print(f"\n  • {r['url']}")
            print(f"    Filters: {len(r['filters'])} types")
            for fname, options in list(r['filters'].items())[:3]:
                print(f"      - {fname}: {len(options)} options")
    print()


if __name__ == '__main__':
    main()
