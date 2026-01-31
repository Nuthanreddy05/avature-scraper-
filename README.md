# Avature Job Scraper - From Zero to 9,400 Jobs

**A production-grade job scraper built from scratch with systematic problem-solving.**

![Python](https://img.shields.io/badge/Python-3.9-blue)
![Jobs Scraped](https://img.shields.io/badge/Jobs_Scraped-9,400-success)
![Sites Processed](https://img.shields.io/badge/Sites_Processed-614-orange)

## 📋 Executive Summary
I built a hybrid web scraping system designed to extract job postings from Avature ATS platforms at scale. My system prioritizes speed and reliability by utilizing advanced fingerprinting and reverse-engineering techniques to uncover hidden APIs before falling back to browser automation.

* **Total Jobs:** 9,400 unique listings
* **Companies:** 66 unique companies (from 614 potential domains)
* **Data Quality:** 100% valid URLs, 89% full description coverage
* **Time Spent:** ~18 hours

---

## 🏗️ What I Built (The Process)

### Phase 1: Discovery (Finding the Haystack)
I used a multi-layered approach to maximize the discovery of Avature-hosted sites beyond the starter pack.
* **Certificate Transparency Logs:** Queried `crt.sh` for SSL certificates issued to `*.avature.net`, uncovering 1,400+ subdomains.
* **Google Dorks:** Automated advanced search queries (e.g., `site:avature.net/careers`, `"powered by Avature"`) to find indexed career portals.
* **Fingerprinting Analysis:** Analyzed site source code to detect the "Dimension" framework (Avature's background technology) on non-standard domains, ensuring white-labeled sites were not missed.

### Phase 2: Reverse Engineering (Unlocking the Data)
I applied 14 distinct reverse-engineering techniques to identify the most robust data extraction methods.
* **Network Analysis:** Inspected Chrome DevTools traffic to map 10 distinct API patterns (e.g., `/api/SearchJobs`).
* **Parameter Manipulation:** Identified and exploited `jobOffset` parameters to bypass UI pagination limits (extracting 1,000+ jobs where the UI showed 20).
* **Header Analysis:** Extracted dynamic API keys and CSRF tokens required for valid JSON requests.
* **Payload Construction:** Replicated complex POST payloads to mimic legitimate user traffic without triggering anti-bot defenses.

### Phase 3: The Hybrid Engine (Architecture)
I implemented a 3-tier cascading architecture to balance speed and coverage:
1.  **Tier 1 (HTTP/API):** Attempts to hit the reverse-engineered JSON endpoints first. (Fastest, low bandwidth).
2.  **Tier 2 (HTML Parsing):** Falls back to standard `BeautifulSoup` parsing if APIs are secured or hidden.
3.  **Tier 3 (Playwright):** Automatically spins up a headless browser only for Single Page Applications (SPAs) that strictly require JavaScript rendering.

### Phase 4: Quality Control
* **Junk Filtering:** Implemented strict exclusion logic for "social share" links (Facebook, Email) often disguised as job posts.
* **Data Normalization:** Standardized 2,002 broken `mailto:` links and converted relative URLs to absolute paths.

---

## ⚙️ Technical Constraints & Decisions

### Why I Did Not Use Proxies
While I am aware that rotating residential proxies (e.g., BrightData) is the standard solution for bypassing rate limits and IP blocking at scale:
* **Decision:** I chose not to use them for this assignment to adhere to zero-cost constraints.
* **Workaround:** Instead, I implemented an intelligent rate-limiter (1 request/second) and user-agent rotation. This successfully processed 614 sites without incurring IP bans, though it limited the maximum concurrency speed.

---

## 🔮 Future Improvements (Scaling to 10k+ Sites)

* **Apollo.io / BuiltWith API:** Automate the "Discovery" phase by pulling pre-validated lists of companies using Avature.
* **Proxy Rotation:** Implement paid proxy rotation to remove the 1 request/second limit, allowing for 100+ concurrent workers.
* **LLM Parsing:** Integrate GPT-4 API to parse unstructured HTML from the 10% of sites that break standard CSS selectors.

---

## 💻 How to Run

1. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   playwright install chromium
