"""
Data Manager Module
Handles saving, loading, and cleanup of scraped job data
"""
import os
import json
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
import glob


class DataManager:
    """Manages local storage of scraped job data"""
    
    def __init__(self, data_dir: str = "data"):
        """
        Initialize data manager
        
        Args:
            data_dir: Directory to store job data files
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        
    def _get_filename(self, timestamp: Optional[datetime] = None) -> str:
        """
        Generate filename for job data
        
        Args:
            timestamp: Datetime for filename, defaults to now
            
        Returns:
            Filename string like 'jobs_2026-01-18_08-00.json'
        """
        if timestamp is None:
            timestamp = datetime.now()
        return f"jobs_{timestamp.strftime('%Y-%m-%d_%H-%M')}.json"
    
    def save_jobs(
        self,
        jobs_data: List[Dict],
        timestamp: Optional[datetime] = None
    ) -> str:
        """
        Save job data to JSON file
        
        Args:
            jobs_data: List of job dictionaries
            timestamp: Timestamp for the file
            
        Returns:
            Path to saved file
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        filename = self._get_filename(timestamp)
        filepath = self.data_dir / filename
        
        # Prepare data for saving
        data_to_save = {
            "timestamp": timestamp.isoformat(),
            "count": len(jobs_data),
            "jobs": jobs_data
        }
        
        # Save as JSON
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Saved {len(jobs_data)} jobs to {filepath}")
        return str(filepath)
    
    def save_jobs_csv(
        self,
        jobs_df: pd.DataFrame,
        timestamp: Optional[datetime] = None
    ) -> str:
        """
        Save job data to CSV file
        
        Args:
            jobs_df: DataFrame with job data
            timestamp: Timestamp for the file
            
        Returns:
            Path to saved file
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        filename = self._get_filename(timestamp).replace('.json', '.csv')
        filepath = self.data_dir / filename
        
        # Save as CSV
        jobs_df.to_csv(filepath, index=False, encoding='utf-8')
        
        print(f"💾 Saved {len(jobs_df)} jobs to {filepath}")
        return str(filepath)
    
    def load_jobs(self, filename: str) -> Dict:
        """
        Load job data from JSON file
        
        Args:
            filename: Name of the file to load
            
        Returns:
            Dictionary with job data
        """
        filepath = self.data_dir / filename
        
        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"📂 Loaded {data.get('count', 0)} jobs from {filepath}")
        return data
    
    def list_data_files(self, extension: str = "json") -> List[Path]:
        """
        List all data files in the data directory
        
        Args:
            extension: File extension to filter (json or csv)
            
        Returns:
            List of Path objects
        """
        pattern = f"jobs_*.{extension}"
        files = list(self.data_dir.glob(pattern))
        files.sort()  # Sort by filename (chronologically)
        return files
    
    def cleanup_old_files(self, days: int = 7) -> int:
        """
        Remove data files older than specified days
        
        Args:
            days: Keep files newer than this many days
            
        Returns:
            Number of files deleted
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        deleted_count = 0
        
        for extension in ['json', 'csv']:
            files = self.list_data_files(extension)
            
            for filepath in files:
                try:
                    # Extract date from filename: jobs_2026-01-18_08-00.json
                    filename = filepath.name
                    date_str = filename.split('_')[1]  # Get '2026-01-18'
                    file_date = datetime.strptime(date_str, '%Y-%m-%d')
                    
                    if file_date < cutoff_date:
                        filepath.unlink()
                        print(f"🗑️  Deleted old file: {filepath.name}")
                        deleted_count += 1
                        
                except (ValueError, IndexError) as e:
                    print(f"⚠️  Skipping file with invalid name: {filepath.name}")
                    continue
        
        if deleted_count > 0:
            print(f"✅ Cleaned up {deleted_count} old files (older than {days} days)")
        else:
            print(f"✅ No old files to clean up")
        
        return deleted_count
    
    def get_statistics(self) -> Dict:
        """
        Get statistics about stored data
        
        Returns:
            Dictionary with statistics
        """
        json_files = self.list_data_files('json')
        csv_files = self.list_data_files('csv')
        
        total_jobs = 0
        for filepath in json_files:
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    total_jobs += data.get('count', 0)
            except:
                continue
        
        # Calculate total size
        total_size = sum(
            f.stat().st_size for f in json_files + csv_files
        )
        
        oldest_file = json_files[0] if json_files else None
        newest_file = json_files[-1] if json_files else None
        
        return {
            "json_files": len(json_files),
            "csv_files": len(csv_files),
            "total_files": len(json_files) + len(csv_files),
            "total_jobs": total_jobs,
            "total_size_mb": total_size / (1024 * 1024),
            "oldest_file": oldest_file.name if oldest_file else None,
            "newest_file": newest_file.name if newest_file else None,
        }
    
    def merge_all_jobs(self, output_file: str = "all_jobs.csv") -> str:
        """
        Merge all job data into a single CSV file
        
        Args:
            output_file: Name of the output file
            
        Returns:
            Path to merged file
        """
        all_jobs = []
        json_files = self.list_data_files('json')
        
        for filepath in json_files:
            try:
                data = self.load_jobs(filepath.name)
                jobs = data.get('jobs', [])
                
                # Add scrape timestamp to each job
                for job in jobs:
                    job['scraped_at'] = data.get('timestamp')
                
                all_jobs.extend(jobs)
            except Exception as e:
                print(f"⚠️  Error loading {filepath.name}: {e}")
                continue
        
        if not all_jobs:
            print("⚠️  No jobs to merge")
            return None
        
        # Create DataFrame and remove duplicates
        df = pd.DataFrame(all_jobs)
        df = df.drop_duplicates(subset=['job_url'], keep='first')
        
        # Save merged file
        output_path = self.data_dir / output_file
        df.to_csv(output_path, index=False, encoding='utf-8')
        
        print(f"📊 Merged {len(df)} unique jobs into {output_path}")
        return str(output_path)


def main():
    """Test the data manager"""
    manager = DataManager()
    
    # Test saving
    test_jobs = [
        {
            "title": "Senior Software Engineer",
            "company": "Google",
            "location": "San Francisco, CA",
            "job_url": "https://example.com/job/1"
        },
        {
            "title": "ML Engineer",
            "company": "OpenAI",
            "location": "San Francisco, CA",
            "job_url": "https://example.com/job/2"
        }
    ]
    
    print("\n📝 Testing save...")
    manager.save_jobs(test_jobs)
    
    print("\n📊 Statistics:")
    stats = manager.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print("\n📂 Listing files:")
    files = manager.list_data_files()
    for f in files:
        print(f"  - {f.name}")
    
    print("\n🗑️  Testing cleanup (30 days)...")
    deleted = manager.cleanup_old_files(days=30)


if __name__ == "__main__":
    main()
