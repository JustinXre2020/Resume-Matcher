"""
Local LLM Filter using LiquidAI/LFM2.5-1.2B-Instruct
Filters jobs based on keyword match, visa sponsorship, and entry-level requirements
"""
import os
import json
from typing import Dict, List, Optional
from pathlib import Path
from huggingface_hub import hf_hub_download
from llama_cpp import Llama
import pandas as pd


class LocalLLMFilter:
    """Filter jobs using local LLM inference"""

    MODEL_REPO = "LiquidAI/LFM2.5-1.2B-Instruct-GGUF"
    MODEL_FILE = "LFM2.5-1.2B-Instruct-Q8_0.gguf"

    def __init__(self, model_dir: str = "models"):
        """
        Initialize the local LLM filter

        Args:
            model_dir: Directory to store downloaded models
        """
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(exist_ok=True)
        self.model_path = self.model_dir / self.MODEL_FILE
        self.llm = None

        # Download model if not exists
        if not self.model_path.exists():
            print(f"📥 Downloading model {self.MODEL_FILE}...")
            self._download_model()

        # Load model
        print(f"🤖 Loading LLM model...")
        self._load_model()
        print(f"✅ LLM model loaded successfully")

    def _download_model(self):
        """Download the GGUF model from HuggingFace"""
        try:
            downloaded_path = hf_hub_download(
                repo_id=self.MODEL_REPO,
                filename=self.MODEL_FILE,
                local_dir=str(self.model_dir)
            )
            print(f"✅ Model downloaded to {downloaded_path}")
        except Exception as e:
            print(f"❌ Failed to download model: {e}")
            raise

    def _load_model(self):
        """Load the GGUF model with llama.cpp"""
        try:
            # Use a reasonable context size that fits in memory
            # The model supports 128K but we'll use 8K to be safe
            n_ctx = 8192

            print(f"   📊 Loading model with n_ctx={n_ctx}...")

            self.llm = Llama(
                model_path=str(self.model_path),
                n_ctx=n_ctx,
                n_threads=8,  # Use more CPU threads
                n_batch=512,  # Batch size for prompt processing
                verbose=True
            )
            print(f"   ✅ Model loaded successfully (context: {n_ctx} tokens)")
        except Exception as e:
            print(f"❌ Failed to load model: {e}")
            raise

    def _safe_str(self, value, default: str = '') -> str:
        """Safely convert value to string, handling NaN/None"""
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return default
        return str(value)

    def _create_prompt(self, job: Dict, search_terms: List[str]) -> str:
        """Create prompt for job evaluation"""
        title = self._safe_str(job.get('title'), 'Unknown')
        company = self._safe_str(job.get('company'), 'Unknown')
        location = self._safe_str(job.get('location'), 'Unknown')
        description = self._safe_str(job.get('description'), '')

        # Truncate description to ~4000 chars (~1000 tokens) to fit in context
        # This leaves room for prompt template and response
        # if len(description) > 4000:
        #     description = description[:4000] + "..."

        search_terms_str = ", ".join(search_terms)

        prompt = f"""Analyze this job posting and answer with JSON only.

Job Title: {title}
Company: {company}
Location: {location}
Description: {description}

Target Roles: {search_terms_str}

Evaluate:
1. keyword_match: Does the job title/description match any target roles? (true/false)
2. visa_sponsorship: Does it mention H1B, visa sponsorship, or NOT explicitly reject sponsorship? (true/false)
3. entry_level: Is this entry-level (0-3 years experience required)? Check for "entry", "junior", "associate", "new grad", or 0-3 years. (true/false)
4. requires_phd: Does it require a PhD or doctorate? (true/false)

Respond ONLY with valid JSON:
{{"keyword_match": true/false, "visa_sponsorship": true/false, "entry_level": true/false, "requires_phd": true/false, "reason": "brief explanation"}}"""

        return prompt

    def evaluate_job(self, job: Dict, search_terms: List[str], _retry: bool = True) -> Dict:
        """
        Evaluate a single job using local LLM

        Args:
            job: Job dictionary
            search_terms: List of target job roles
            _retry: Internal flag for retry with truncation

        Returns:
            Evaluation result with pass/fail and reasons
        """
        try:
            # Skip jobs with no description - can't evaluate them properly
            desc = self._safe_str(job.get('description'), '')
            if not desc or len(desc) < 50:
                print(f"   ⏭️ Skipping {job.get('title', 'Unknown')[:40]} - no/short description ({len(desc)} chars)")
                return {
                    "keyword_match": False,
                    "visa_sponsorship": False,
                    "entry_level": False,
                    "requires_phd": False,
                    "reason": "No description available - skipped",
                    "skipped": True
                }

            prompt = self._create_prompt(job, search_terms)

            # Debug: print prompt stats
            prompt_len = len(prompt)
            print(f"   📝 Job: {job.get('title', 'Unknown')[:40]} | Prompt: {prompt_len} chars | Desc: {len(desc)} chars")

            # Reset KV cache to avoid state corruption between requests
            self.llm.reset()

            # Use chat completion format for this instruction-tuned model
            messages = [
                {"role": "system", "content": "You are a job posting analyzer. Respond only with valid JSON."},
                {"role": "user", "content": prompt}
            ]

            response = self.llm.create_chat_completion(
                messages=messages,
                max_tokens=256,
                temperature=0.1,
            )

            response_text = response['choices'][0]['message']['content'].strip()
            finish_reason = response['choices'][0].get('finish_reason', 'unknown')
            print(f"   ✅ Response: {len(response_text)} chars, finish: {finish_reason}")
            if response_text:
                print(f"   📄 Raw response: {response_text[:200]}...")

            # Parse JSON from response
            result = self._parse_response(response_text)
            result['job_title'] = job.get('title', 'Unknown')
            result['company'] = job.get('company', 'Unknown')

            return result

        except Exception as e:
            import traceback
            error_msg = str(e)
            desc = self._safe_str(job.get('description'), '')
            prompt = self._create_prompt(job, search_terms)

            # Debug: print detailed error info
            print(f"   ❌ ERROR for {job.get('title', 'Unknown')[:40]}")
            print(f"      Error type: {type(e).__name__}")
            print(f"      Error msg: {error_msg}")
            print(f"      Prompt length: {len(prompt)} chars")
            print(f"      Description length: {len(desc)} chars")
            print(f"      Full traceback:")
            traceback.print_exc()

            # Estimate token count (rough: ~4 chars per token)
            estimated_tokens = len(prompt) // 4
            print(f"      Estimated tokens: ~{estimated_tokens}")
            print(f"      Model n_ctx: {self.llm.n_ctx()}")

            # If context overflow, retry with truncated description
            if "llama_decode returned -1" in error_msg and _retry:
                # Try with much shorter description
                if len(desc) > 1500:
                    print(f"      🔄 Retrying with truncated description (1500 chars)...")
                    truncated_job = job.copy()
                    truncated_job['description'] = desc[:1500] + "..."
                    return self.evaluate_job(truncated_job, search_terms, _retry=False)

            print(f"⚠️ LLM evaluation error for {job.get('title', 'Unknown')}: {e}")
            # Default to pass on error (let rule-based filter handle it)
            return {
                "keyword_match": True,
                "visa_sponsorship": True,
                "entry_level": True,
                "requires_phd": False,
                "reason": f"LLM error: {str(e)[:50]}",
                "error": True
            }

    def _parse_response(self, response_text: str) -> Dict:
        """Parse LLM response into structured result"""
        try:
            # Try to find JSON in response
            start = response_text.find('{')
            end = response_text.rfind('}') + 1

            if start >= 0 and end > start:
                json_str = response_text[start:end]
                result = json.loads(json_str)

                # Ensure all required fields exist
                return {
                    "keyword_match": result.get("keyword_match", True),
                    "visa_sponsorship": result.get("visa_sponsorship", True),
                    "entry_level": result.get("entry_level", True),
                    "requires_phd": result.get("requires_phd", False),
                    "reason": result.get("reason", "")
                }
            else:
                # Fallback parsing
                response_lower = response_text.lower()
                return {
                    "keyword_match": "keyword_match\": true" in response_lower or "keyword_match\":true" in response_lower,
                    "visa_sponsorship": "visa_sponsorship\": true" in response_lower or "no sponsor" not in response_lower,
                    "entry_level": "entry_level\": true" in response_lower,
                    "requires_phd": "requires_phd\": true" in response_lower,
                    "reason": "Parsed from text response"
                }

        except json.JSONDecodeError:
            # Default to permissive on parse error
            return {
                "keyword_match": True,
                "visa_sponsorship": True,
                "entry_level": True,
                "requires_phd": False,
                "reason": "JSON parse error - defaulting to pass"
            }

    def should_include_job(self, evaluation: Dict) -> bool:
        """Determine if job should be included based on evaluation"""
        return (
            evaluation.get("keyword_match", False) and
            evaluation.get("visa_sponsorship", False) and
            evaluation.get("entry_level", False) and
            not evaluation.get("requires_phd", True)
        )

    def filter_jobs(
        self,
        jobs_list: List[Dict],
        search_terms: List[str],
        verbose: bool = True
    ) -> List[Dict]:
        """
        Filter jobs using local LLM

        Args:
            jobs_list: List of job dictionaries
            search_terms: Target job roles to match
            verbose: Print progress

        Returns:
            Filtered list of jobs that pass all criteria
        """
        filtered = []
        excluded_keyword = 0
        excluded_visa = 0
        excluded_experience = 0
        excluded_phd = 0
        skipped = 0

        total = len(jobs_list)

        for i, job in enumerate(jobs_list, 1):
            if verbose and i % 10 == 0:
                print(f"   🤖 Evaluating {i}/{total}...")

            evaluation = self.evaluate_job(job, search_terms)

            # Track skipped jobs (no description)
            if evaluation.get("skipped", False):
                skipped += 1
                continue

            if not evaluation.get("keyword_match", False):
                excluded_keyword += 1
                continue

            if not evaluation.get("visa_sponsorship", False):
                excluded_visa += 1
                continue

            if not evaluation.get("entry_level", False):
                excluded_experience += 1
                continue

            if evaluation.get("requires_phd", False):
                excluded_phd += 1
                continue

            # Job passed all filters
            job['llm_evaluation'] = evaluation
            filtered.append(job)

        print(f"   Skipped {skipped} jobs (no description)")
        print(f"   Excluded {excluded_keyword} jobs (keyword mismatch)")
        print(f"   Excluded {excluded_visa} jobs (no visa sponsorship)")
        print(f"   Excluded {excluded_experience} jobs (not entry-level)")
        print(f"   Excluded {excluded_phd} jobs (PhD required)")
        print(f"   ✅ {len(filtered)} jobs passed LLM filter")

        return filtered


def main():
    """Test the LLM filter"""
    filter = LocalLLMFilter()

    # Test job
    test_job = {
        "title": "Junior Data Analyst",
        "company": "Google",
        "location": "San Francisco, CA",
        "description": """
        We are looking for a Junior Data Analyst to join our team.

        Requirements:
        - Bachelor's degree in Statistics, Mathematics, or related field
        - 0-2 years of experience
        - Proficiency in SQL and Python

        We offer H1B visa sponsorship for qualified candidates.
        """
    }

    search_terms = ["data analyst", "product manager", "data scientist"]

    result = filter.evaluate_job(test_job, search_terms)
    print("\n📊 Evaluation Result:")
    print(json.dumps(result, indent=2))

    print(f"\n✅ Should include: {filter.should_include_job(result)}")


if __name__ == "__main__":
    main()
