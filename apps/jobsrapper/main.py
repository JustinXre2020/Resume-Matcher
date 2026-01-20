"""
Job Hunter Sentinel - Main Orchestration Script
Coordinates scraping, deduplication, and email dispatch
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
from llm_filter import LocalLLMFilter

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

            # Configuration
            self.search_terms = self._get_list_config("SEARCH_TERMS", ["entry level software engineer"])
            self.locations = self._get_list_config("LOCATIONS", ["San Francisco, CA"])
            self.results_wanted = int(os.getenv("RESULTS_WANTED", "20"))
            self.hours_old = int(os.getenv("HOURS_OLD", "24"))
            self.use_llm_filter = os.getenv("USE_LLM_FILTER", "true").lower() == "true"

            # Initialize LLM filter if enabled
            self.llm_filter = None
            if self.use_llm_filter:
                print("🤖 Initializing Local LLM Filter...")
                self.llm_filter = LocalLLMFilter()

            print(f"✅ Configuration loaded:")
            print(f"   Search Terms: {self.search_terms}")
            print(f"   Locations: {self.locations}")
            print(f"   Results Wanted: {self.results_wanted}")
            print(f"   Time Window: {self.hours_old} hours")
            print(f"   LLM Filter: {'Enabled' if self.use_llm_filter else 'Disabled'}")

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
        """Execute the full job hunting workflow"""
        start_time = datetime.now()
        print(f"\n{'='*60}")
        print(f"🎯 Job Hunter Sentinel - Daily Run")
        print(f"⏰ Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")

        try:
            # Step 1: Scrape Jobs
            print("\n📡 STEP 1: Scraping job postings...")
            print("-" * 60)
            jobs_df = self.scraper.scrape_multiple_queries(
                search_terms=self.search_terms,
                locations=self.locations,
                results_wanted=self.results_wanted,
                hours_old=self.hours_old
            )

            if jobs_df.empty:
                print("\n⚠️ No jobs found. Sending empty notification...")
                self.email_sender.send_empty_notification()
                self._print_summary(start_time, 0, 0)
                return

            print(f"\n✅ Scraped {len(jobs_df)} total jobs")

            # Step 2: LLM-based filtering for entry-level and H1B-friendly jobs
            print(f"\n🤖 STEP 2: LLM filtering (entry-level & H1B)...")
            print("-" * 60)
            jobs_list = jobs_df.to_dict('records')
            
            if self.llm_filter:
                # Extract base search terms (without level modifiers)
                base_terms = self._get_base_search_terms()
                filtered_jobs = self.llm_filter.filter_jobs(jobs_list, base_terms)
            else:
                print("⚠️ LLM filter not available, using rule-based fallback...")
                filtered_jobs = self.filter_jobs(jobs_list)

            if not filtered_jobs:
                print("\n⚠️ No jobs passed LLM filters. Sending empty notification...")
                self.email_sender.send_empty_notification()
                self._print_summary(start_time, len(jobs_df), 0)
                return

            # Step 3: Save filtered data to local files
            print(f"\n💾 STEP 3: Saving filtered data to local storage...")
            print("-" * 60)
            self.data_manager.save_jobs(filtered_jobs, timestamp=start_time)
            filtered_df = pd.DataFrame(filtered_jobs)
            self.data_manager.save_jobs_csv(filtered_df, timestamp=start_time)

            # Cleanup old data files (older than 7 days)
            self.data_manager.cleanup_old_files(days=7)

            # Step 4: Deduplication
            print(f"\n🔍 STEP 4: Checking for duplicate jobs...")
            print("-" * 60)
            new_jobs = self.database.filter_new_jobs(filtered_jobs)

            if not new_jobs:
                print("\n⚠️ All jobs were already sent. No new jobs to dispatch.")
                self._print_summary(start_time, len(jobs_df), 0)
                return

            # Step 5: Send Email
            print(f"\n📧 STEP 5: Sending email digest...")
            print("-" * 60)
            email_sent = self.email_sender.send_daily_digest(new_jobs)

            if not email_sent:
                print("❌ Email dispatch failed!")
                self._print_summary(start_time, len(jobs_df), 0)
                return

            # Step 6: Mark as sent in database
            print(f"\n💾 STEP 6: Marking jobs as sent in database...")
            print("-" * 60)
            for job in new_jobs:
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

            print(f"✅ Marked {len(new_jobs)} jobs as sent")

            # Step 7: Show data storage statistics
            print(f"\n📊 STEP 7: Data storage statistics...")
            print("-" * 60)
            stats = self.data_manager.get_statistics()
            print(f"   Total files: {stats['total_files']} ({stats['json_files']} JSON, {stats['csv_files']} CSV)")
            print(f"   Total jobs stored: {stats['total_jobs']}")
            print(f"   Storage size: {stats['total_size_mb']:.2f} MB")
            print(f"   Oldest file: {stats['oldest_file']}")
            print(f"   Newest file: {stats['newest_file']}")

            # Summary
            self._print_summary(start_time, len(jobs_df), len(new_jobs))

        except KeyboardInterrupt:
            print("\n\n⚠️ Process interrupted by user")
            sys.exit(0)
        except Exception as e:
            print(f"\n\n❌ Fatal error: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    def _get_base_search_terms(self) -> List[str]:
        """Extract base search terms without level modifiers for LLM matching"""
        base_terms = set()
        level_modifiers = [
            'entry level', 'entry-level', 'junior', 'associate', 'new grad',
            'new graduate', 'early career', 'graduate'
        ]

        for term in self.search_terms:
            term_lower = term.lower()
            # Remove level modifiers to get base role
            base_term = term_lower
            for modifier in level_modifiers:
                base_term = base_term.replace(modifier, '').strip()

            if base_term:
                base_terms.add(base_term)

        return list(base_terms)

    def _print_summary(self, start_time: datetime, scraped: int, sent: int):
        """Print execution summary"""
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        print(f"\n{'='*60}")
        print(f"📊 EXECUTION SUMMARY")
        print(f"{'='*60}")
        print(f"⏱️  Duration: {duration:.1f} seconds")
        print(f"📡 Jobs Scraped: {scraped}")
        print(f"📧 Jobs Sent: {sent}")
        print(f"✅ Status: {'SUCCESS' if sent > 0 else 'NO NEW JOBS'}")
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
