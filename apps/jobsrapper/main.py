"""
Job Hunter Sentinel - Main Orchestration Script
Coordinates scraping, deduplication, and email dispatch
Supports multi-recipient with per-recipient search terms and sponsorship filtering
"""
import os
import sys
from typing import List, Dict
from datetime import datetime
from dotenv import load_dotenv
import pandas as pd

# Import custom modules
from scraper import JobScraper
from database import JobDatabase
from email_sender import EmailSender
from data_manager import DataManager
from llm_filter import OpenRouterLLMFilter
from config import parse_recipients, get_all_search_terms

load_dotenv()

# Entry-level job title keywords
ENTRY_LEVEL_KEYWORDS = [
    'entry level', 'entry-level', 'junior', 'associate', 'new grad',
    'new graduate', 'early career', 'graduate', 'i ', ' i,', ' 1 ', ' 1,',
    'level 1', 'level i', 'trainee', 'intern'
]

# Senior-level keywords to exclude
SENIOR_KEYWORDS = [
    'senior', 'sr.', 'sr ', 'lead', 'principal', 'staff', 'manager',
    'director', 'vp', 'vice president', 'head of', 'chief', 'architect',
    'ii', 'iii', 'iv', ' 2 ', ' 3 ', ' 4 ', 'level 2', 'level 3'
]

# PhD requirement keywords to exclude
PHD_KEYWORDS = [
    'phd', 'ph.d', 'doctorate', 'doctoral', 'postdoc', 'post-doc',
    'research scientist', 'research engineer'
]

# H1B/Visa sponsorship keywords
VISA_KEYWORDS = [
    'h1b', 'h-1b', 'visa sponsor', 'sponsorship', 'work authorization',
    'immigration', 'sponsor', 'employment authorization'
]


class JobHunterSentinel:
    """Main orchestrator for the job hunting automation system"""

    def __init__(self):
        """Initialize all components"""
        print("🚀 Initializing Job Hunter Sentinel...")

        try:
            self.scraper = JobScraper()
            self.database = JobDatabase()
            self.email_sender = EmailSender()
            self.data_manager = DataManager()

            # Load recipients and their search terms
            self.recipients = parse_recipients()
            self.all_search_terms = get_all_search_terms(self.recipients)

            # Configuration
            self.locations = self._get_list_config("LOCATIONS", ["San Francisco, CA"])
            self.results_wanted = int(os.getenv("RESULTS_WANTED", "20"))
            self.hours_old = int(os.getenv("HOURS_OLD", "24"))
            self.use_llm_filter = os.getenv("USE_LLM_FILTER", "true").lower() == "true"
            self.llm_workers = int(os.getenv("LLM_WORKERS", "0"))  # 0 = auto-detect based on RAM

            # Initialize LLM filter if enabled
            self.llm_filter = None
            if self.use_llm_filter:
                print("🤖 Initializing OpenRouter LLM Filter...")
                self.llm_filter = OpenRouterLLMFilter()

            print(f"✅ Configuration loaded:")
            print(f"   Recipients: {len(self.recipients)}")
            for r in self.recipients:
                print(f"     - {r.email} (needs_sponsorship={r.needs_sponsorship}, terms={r.search_terms})")
            print(f"   All Search Terms: {self.all_search_terms}")
            print(f"   Locations: {self.locations}")
            print(f"   Results Wanted: {self.results_wanted}")
            print(f"   Time Window: {self.hours_old} hours")
            print(f"   LLM Filter: {'Enabled' if self.use_llm_filter else 'Disabled'}")
            print(f"   LLM Workers: {self.llm_workers if self.llm_workers > 0 else 'auto'}")

        except Exception as e:
            print(f"❌ Initialization failed: {e}")
            sys.exit(1)

    def _get_list_config(self, key: str, default: List[str]) -> List[str]:
        """Parse comma-separated config value"""
        value = os.getenv(key)
        if not value:
            return default
        return [item.strip() for item in value.split(",") if item.strip()]

    def _is_entry_level(self, title: str) -> bool:
        """Check if job title indicates entry-level position"""
        if not title:
            return False
        title_lower = title.lower()

        # Exclude if senior keywords found
        for keyword in SENIOR_KEYWORDS:
            if keyword in title_lower:
                return False

        # Include if entry-level keywords found
        for keyword in ENTRY_LEVEL_KEYWORDS:
            if keyword in title_lower:
                return True

        # Default: include jobs without explicit level (could be entry-level)
        return True

    def _has_visa_sponsorship(self, description: str) -> bool:
        """Check if job description mentions visa sponsorship"""
        if not description or (isinstance(description, float) and pd.isna(description)):
            return True  # Include jobs without description (can't verify)

        desc_lower = str(description).lower()

        # Check for visa sponsorship keywords
        for keyword in VISA_KEYWORDS:
            if keyword in desc_lower:
                return True

        # Check for negative visa statements (exclude these)
        negative_patterns = [
            'no sponsor', 'not sponsor', 'cannot sponsor', 'will not sponsor',
            'unable to sponsor', 'without sponsor', 'no visa', 'not able to sponsor'
        ]
        for pattern in negative_patterns:
            if pattern in desc_lower:
                return False

        # Default: include jobs that don't explicitly reject sponsorship
        return True

    def _requires_phd(self, title: str, description: str) -> bool:
        """Check if job requires PhD"""
        title_lower = title.lower() if title else ''
        desc_lower = str(description).lower() if description and not (isinstance(description, float) and pd.isna(description)) else ''

        # Check for PhD keywords in title (strong indicator)
        for keyword in PHD_KEYWORDS:
            if keyword in title_lower:
                return True

        # Check for PhD requirement phrases in description
        phd_required_patterns = [
            'phd required', 'ph.d required', 'ph.d. required',
            'doctorate required', 'doctoral degree required',
            'must have phd', 'must have ph.d', 'requires phd', 'requires ph.d',
            'phd in', 'ph.d in', 'ph.d. in'
        ]
        for pattern in phd_required_patterns:
            if pattern in desc_lower:
                return True

        return False

    def filter_jobs(self, jobs_list: List[Dict]) -> List[Dict]:
        """Filter jobs for entry-level positions with potential visa sponsorship"""
        filtered = []
        excluded_senior = 0
        excluded_no_visa = 0
        excluded_phd = 0

        for job in jobs_list:
            title = job.get('title', '')
            description = job.get('description', '')

            # Check entry-level
            if not self._is_entry_level(title):
                excluded_senior += 1
                continue

            # Check PhD requirement
            if self._requires_phd(title, description):
                excluded_phd += 1
                continue

            # Check visa sponsorship
            if not self._has_visa_sponsorship(description):
                excluded_no_visa += 1
                continue

            filtered.append(job)

        print(f"   Excluded {excluded_senior} senior-level positions")
        print(f"   Excluded {excluded_phd} PhD-required positions")
        print(f"   Excluded {excluded_no_visa} jobs with no visa sponsorship")
        print(f"   ✅ {len(filtered)} jobs passed filters")

        return filtered

    def run(self):
        """Execute the full job hunting workflow with sequential keyword processing"""
        start_time = datetime.now()
        print(f"\n{'='*60}")
        print(f"🎯 Job Hunter Sentinel - Daily Run")
        print(f"⏰ Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")

        try:
            # Track jobs by search term for per-recipient filtering
            jobs_by_term: Dict[str, List[Dict]] = {}
            total_scraped = 0
            total_new = 0
            total_filtered = 0

            # Process each search term sequentially
            for term_idx, search_term in enumerate(self.all_search_terms, 1):
                print(f"\n{'='*60}")
                print(f"🔍 Processing search term {term_idx}/{len(self.all_search_terms)}: '{search_term}'")
                print(f"{'='*60}")

                # Step 1: Scrape Jobs for THIS keyword only
                print(f"\n📡 STEP 1: Scraping job postings for '{search_term}'...")
                print("-" * 60)
                jobs_df = self.scraper.scrape_multiple_queries(
                    search_terms=[search_term],
                    locations=self.locations,
                    results_wanted=self.results_wanted,
                    hours_old=self.hours_old
                )

                if jobs_df.empty:
                    print(f"   ⚠️ No jobs found for '{search_term}'")
                    jobs_by_term[search_term] = []
                    continue

                scraped_count = len(jobs_df)
                total_scraped += scraped_count
                print(f"   ✅ Scraped {scraped_count} jobs for '{search_term}'")

                # Step 2: Deduplication (before LLM filtering to save inference time)
                print(f"\n🔍 STEP 2: Checking for duplicate jobs...")
                print("-" * 60)
                jobs_list = jobs_df.to_dict('records')
                new_jobs = self.database.filter_new_jobs(jobs_list)

                if not new_jobs:
                    print(f"   ⚠️ All jobs for '{search_term}' were already sent")
                    jobs_by_term[search_term] = []
                    continue

                new_count = len(new_jobs)
                total_new += new_count
                print(f"   ✅ {new_count} new jobs for '{search_term}'")

                # Step 2.5: Save ALL new jobs before filtering (for data collection)
                print(f"\n💾 Saving {new_count} new jobs to storage...")
                safe_term = search_term.replace(' ', '_').replace('/', '_')[:30]
                self.data_manager.save_jobs(new_jobs, timestamp=start_time, prefix=f"all_jobs_{safe_term}")

                # Step 3: LLM-based filtering for entry-level and H1B-friendly jobs
                print(f"\n🤖 STEP 3: LLM filtering for '{search_term}'...")
                print("-" * 60)

                if self.llm_filter:
                    # Use parallel filtering (auto-detects workers based on RAM if llm_workers=0)
                    filtered_jobs = self.llm_filter.filter_jobs_parallel(
                        new_jobs, [search_term], num_workers=self.llm_workers
                    )
                else:
                    print("   ⚠️ LLM filter not available, using rule-based fallback...")
                    filtered_jobs = self.filter_jobs(new_jobs)

                filtered_count = len(filtered_jobs)
                total_filtered += filtered_count
                print(f"   ✅ {filtered_count} jobs passed filters for '{search_term}'")

                # Store filtered jobs for this term
                jobs_by_term[search_term] = filtered_jobs

                # Save filtered data
                if filtered_jobs:
                    self.data_manager.save_jobs(filtered_jobs, timestamp=start_time, prefix=f"filtered_jobs_{safe_term}")

            # Check if we have any jobs to send
            all_jobs_count = sum(len(jobs) for jobs in jobs_by_term.values())

            if all_jobs_count == 0:
                print("\n⚠️ No jobs passed filters across all search terms. Sending empty notification...")
                self.email_sender.send_empty_notification()
                self._print_summary(start_time, total_scraped, 0, {})
                return

            # Step 4: Send Emails (per-recipient filtering by term + sponsorship)
            print(f"\n📧 STEP 4: Sending email digests to {len(self.recipients)} recipient(s)...")
            print("-" * 60)
            email_results = self.email_sender.send_daily_digest(jobs_by_term)

            # Step 5: Mark ALL unique jobs as sent (regardless of recipient)
            print(f"\n💾 STEP 5: Marking jobs as sent in database...")
            print("-" * 60)

            # Collect all unique jobs across all terms
            all_unique_jobs = []
            seen_urls = set()
            for jobs in jobs_by_term.values():
                for job in jobs:
                    url = job.get('job_url')
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_unique_jobs.append(job)

            for job in all_unique_jobs:
                self.database.mark_as_sent(
                    job_url=job.get('job_url', ''),
                    title=job.get('title', ''),
                    company=job.get('company', ''),
                    location=job.get('location', ''),
                    score=0,
                    metadata={
                        'site': job.get('site', '')
                    }
                )

            print(f"   ✅ Marked {len(all_unique_jobs)} unique jobs as sent")

            # Step 6: Show data storage statistics
            print(f"\n📊 STEP 6: Data storage statistics...")
            print("-" * 60)
            stats = self.data_manager.get_statistics()
            print(f"   Total files: {stats['total_files']} ({stats['json_files']} JSON, {stats['csv_files']} CSV)")
            print(f"   Total jobs stored: {stats['total_jobs']}")
            print(f"   Storage size: {stats['total_size_mb']:.2f} MB")
            print(f"   Oldest file: {stats['oldest_file']}")
            print(f"   Newest file: {stats['newest_file']}")

            # Cleanup old data files (older than 7 days)
            self.data_manager.cleanup_old_files(days=7)

            # Summary
            self._print_summary(start_time, total_scraped, total_filtered, email_results)

        except KeyboardInterrupt:
            print("\n\n⚠️ Process interrupted by user")
            sys.exit(0)
        except Exception as e:
            print(f"\n\n❌ Fatal error: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    def _print_summary(
        self,
        start_time: datetime,
        scraped: int,
        filtered: int,
        email_results: Dict[str, bool]
    ):
        """Print execution summary"""
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # Calculate email stats
        total_recipients = len(email_results) if email_results else 0
        successful_emails = sum(1 for success in email_results.values() if success) if email_results else 0

        print(f"\n{'='*60}")
        print(f"📊 EXECUTION SUMMARY")
        print(f"{'='*60}")
        print(f"⏱️  Duration: {duration:.1f} seconds")
        print(f"📡 Jobs Scraped: {scraped}")
        print(f"🔍 Jobs Filtered: {filtered}")
        print(f"📧 Email Results: {successful_emails}/{total_recipients} successful")

        if email_results:
            for email, success in email_results.items():
                status = "✅" if success else "❌"
                print(f"   {status} {email}")

        overall_status = 'SUCCESS' if filtered > 0 and successful_emails > 0 else 'NO NEW JOBS'
        print(f"✅ Status: {overall_status}")
        print(f"{'='*60}\n")


def main():
    """Main entry point"""
    try:
        sentinel = JobHunterSentinel()
        sentinel.run()
    except Exception as e:
        print(f"\n❌ Application failed to start: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
