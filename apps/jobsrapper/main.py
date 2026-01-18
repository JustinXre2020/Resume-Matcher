"""
Job Hunter Sentinel - Main Orchestration Script
Coordinates scraping, analysis, deduplication, and email dispatch
"""
import os
import sys
from typing import List, Dict
from datetime import datetime
from dotenv import load_dotenv

# Import custom modules
from scraper import JobScraper
from ai_analyzer import AIAnalyzer
from database import JobDatabase
from email_sender import EmailSender
from data_manager import DataManager

load_dotenv()


class JobHunterSentinel:
    """Main orchestrator for the job hunting automation system"""
    
    def __init__(self):
        """Initialize all components"""
        print("🚀 Initializing Job Hunter Sentinel...")
        
        try:
            self.scraper = JobScraper()
            self.analyzer = AIAnalyzer()
            self.database = JobDatabase()
            self.email_sender = EmailSender()
            self.data_manager = DataManager()
            
            # Configuration
            self.search_terms = self._get_list_config("SEARCH_TERMS", ["software engineer"])
            self.locations = self._get_list_config("LOCATIONS", ["San Francisco, CA"])
            self.results_wanted = int(os.getenv("RESULTS_WANTED", "20"))
            self.hours_old = int(os.getenv("HOURS_OLD", "24"))
            self.min_score = int(os.getenv("MIN_SCORE", "6"))
            
            print(f"✅ Configuration loaded:")
            print(f"   Search Terms: {self.search_terms}")
            print(f"   Locations: {self.locations}")
            print(f"   Results Wanted: {self.results_wanted}")
            print(f"   Time Window: {self.hours_old} hours")
            print(f"   Min Score: {self.min_score}/10")
            
        except Exception as e:
            print(f"❌ Initialization failed: {e}")
            sys.exit(1)
    
    def _get_list_config(self, key: str, default: List[str]) -> List[str]:
        """Parse comma-separated config value"""
        value = os.getenv(key)
        if not value:
            return default
        return [item.strip() for item in value.split(",") if item.strip()]
    
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
                self._print_summary(start_time, 0, 0, 0)
                return
            
            print(f"\n✅ Scraped {len(jobs_df)} total jobs")
            
            # Save raw scraped data to local files
            print(f"\n💾 Saving raw data to local storage...")
            print("-" * 60)
            jobs_list = jobs_df.to_dict('records')
            self.data_manager.save_jobs(jobs_list, timestamp=start_time)
            self.data_manager.save_jobs_csv(jobs_df, timestamp=start_time)
            
            # Cleanup old data files (older than 7 days)
            self.data_manager.cleanup_old_files(days=7)
            
            # Step 2: Convert to dict format for processing
            jobs_list = jobs_df.to_dict('records')
            
            # Step 3: AI Analysis
            print("\n🤖 STEP 2: Analyzing jobs with AI...")
            print("-" * 60)
            analyzed_jobs = self.analyzer.analyze_batch(jobs_list, delay_between_calls=1.0)
            
            # Step 4: Filter by score
            print(f"\n🎯 STEP 3: Filtering by score (>= {self.min_score})...")
            print("-" * 60)
            high_scoring_jobs = self.analyzer.filter_by_score(
                analyzed_jobs,
                min_score=self.min_score
            )
            
            if not high_scoring_jobs:
                print("\n⚠️ No jobs met the score threshold. Sending empty notification...")
                self.email_sender.send_empty_notification()
                self._print_summary(start_time, len(jobs_df), len(analyzed_jobs), 0)
                return
            
            # Step 5: Deduplication
            print(f"\n🔍 STEP 4: Checking for duplicate jobs...")
            print("-" * 60)
            new_jobs = self.database.filter_new_jobs(high_scoring_jobs)
            
            if not new_jobs:
                print("\n⚠️ All high-scoring jobs were already sent. No new jobs to dispatch.")
                self._print_summary(start_time, len(jobs_df), len(analyzed_jobs), 0)
                return
            
            # Step 6: Fetch LinkedIn details for top jobs (optional)
            print(f"\n📄 STEP 5: Fetching detailed descriptions...")
            print("-" * 60)
            # Extract job_data for jobs that need detailed descriptions
            jobs_needing_details = [
                job.get('job_data', job) for job in new_jobs 
                if job.get('job_data', {}).get('site') == 'linkedin'
            ]
            
            if jobs_needing_details:
                print(f"Fetching details for {len(jobs_needing_details)} LinkedIn jobs...")
                # This would update the descriptions in-place
                # For now, we skip to avoid rate limits unless explicitly needed
                print("⏭️ Skipping detailed fetch (enable if needed)")
            
            # Step 7: Send Email
            print(f"\n📧 STEP 6: Sending email digest...")
            print("-" * 60)
            email_sent = self.email_sender.send_daily_digest(new_jobs)
            
            if not email_sent:
                print("❌ Email dispatch failed!")
                self._print_summary(start_time, len(jobs_df), len(analyzed_jobs), 0)
                return
            
            # Step 8: Mark as sent in database
            print(f"\n💾 STEP 7: Marking jobs as sent in database...")
            print("-" * 60)
            for job in new_jobs:
                job_data = job.get('job_data', job)
                self.database.mark_as_sent(
                    job_url=job_data.get('job_url'),
                    title=job_data.get('title', ''),
                    company=job_data.get('company', ''),
                    location=job_data.get('location', ''),
                    score=job.get('score', 0),
                    metadata={
                        'summary': job.get('summary', ''),
                        'site': job_data.get('site', '')
                    }
                )
            
            print(f"✅ Marked {len(new_jobs)} jobs as sent")
            
            # Step 9: Show data storage statistics
            print(f"\n📊 STEP 8: Data storage statistics...")
            print("-" * 60)
            stats = self.data_manager.get_statistics()
            print(f"   Total files: {stats['total_files']} ({stats['json_files']} JSON, {stats['csv_files']} CSV)")
            print(f"   Total jobs stored: {stats['total_jobs']}")
            print(f"   Storage size: {stats['total_size_mb']:.2f} MB")
            print(f"   Oldest file: {stats['oldest_file']}")
            print(f"   Newest file: {stats['newest_file']}")
            
            # Summary
            self._print_summary(start_time, len(jobs_df), len(analyzed_jobs), len(new_jobs))
            
        except KeyboardInterrupt:
            print("\n\n⚠️ Process interrupted by user")
            sys.exit(0)
        except Exception as e:
            print(f"\n\n❌ Fatal error: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    def _print_summary(self, start_time: datetime, scraped: int, analyzed: int, sent: int):
        """Print execution summary"""
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print(f"\n{'='*60}")
        print(f"📊 EXECUTION SUMMARY")
        print(f"{'='*60}")
        print(f"⏱️  Duration: {duration:.1f} seconds")
        print(f"📡 Jobs Scraped: {scraped}")
        print(f"🤖 Jobs Analyzed: {analyzed}")
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
