"""
OpenRouter LLM Filter using async API calls
Filters jobs based on keyword match, visa sponsorship, and entry-level requirements
Supports asyncio for concurrent inference

OLD LOCAL INFERENCE LOGIC IS PRESERVED AT THE BOTTOM OF THIS FILE
"""
import os
import json
import asyncio
import logging
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv
import aiohttp
import pandas as pd

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# OpenRouter API Configuration
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "liquid/lfm-2.5-1.2b-instruct")


class OpenRouterError(Exception):
    """Custom exception for OpenRouter API errors."""
    pass


def _safe_str(value: Any, default: str = '') -> str:
    """Safely convert value to string, handling NaN/None"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    return str(value)


def _create_prompt(job: Dict, search_terms: List[str]) -> str:
    """Create prompt for job evaluation"""
    title = _safe_str(job.get('title'), 'Unknown')
    company = _safe_str(job.get('company'), 'Unknown')
    location = _safe_str(job.get('location'), 'Unknown')
    description = _safe_str(job.get('description'), '')
    search_terms_str = ", ".join(search_terms)

    prompt = f"""Analyze this job posting and answer with JSON only.

Job Title: {title}
Company: {company}
Location: {location}
Description: {description}

Target Roles: {search_terms_str}

Evaluate:
1. keyword_match: Does the job title/description match any target roles? That is, does one of the target roles, which are separated by a comma, exist in the job title/description? (true/false)
2. visa_sponsorship: Does it mention H1B, visa sponsorship, or NOT explicitly reject sponsorship? (true/false)
3. entry_level: Is this entry-level (0-3 years experience required)? keywords including "entry", "junior", "associate", "new grad", or "0-3 years of experience" should be true. keywords like
    senior, mid-level, Sr., staff, principal should be considered false. (true/false)
4. requires_phd: Does it require a PhD or doctorate? (true/false)
5. is_internship: Is this an internship position? Look for keywords like "intern", "internship", "co-op", or "summer program". (true/false)

Respond ONLY with valid JSON:
{{"keyword_match": true/false, "visa_sponsorship": true/false, "entry_level": true/false, "requires_phd": true/false, "is_internship": true/false, "reason": "brief explanation"}}"""

    return prompt


def _parse_response(response_text: str) -> Dict:
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
                "is_internship": result.get("is_internship", False),
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
                "is_internship": "is_internship\": true" in response_lower,
                "reason": "Parsed from text response"
            }

    except json.JSONDecodeError:
        # Default to permissive on parse error
        return {
            "keyword_match": True,
            "visa_sponsorship": True,
            "entry_level": True,
            "requires_phd": False,
            "is_internship": False,
            "reason": "JSON parse error - defaulting to pass"
        }


async def _call_openrouter(
    messages: List[Dict[str, str]],
    model: str = OPENROUTER_MODEL,
    temperature: float = 0.1,
    max_tokens: int = 256,
    session: Optional[aiohttp.ClientSession] = None,
) -> str:
    """
    Make an async call to OpenRouter API.

    Args:
        messages: List of message dicts with 'role' and 'content' keys.
        model: OpenRouter model identifier.
        temperature: Sampling temperature (0-1).
        max_tokens: Maximum tokens in response.
        session: Optional aiohttp session for connection reuse.

    Returns:
        The assistant's response content.

    Raises:
        OpenRouterError: If the API call fails.
    """
    if not OPENROUTER_API_KEY:
        raise OpenRouterError("OPENROUTER_API_KEY environment variable not set")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://resume-matcher.app",
        "X-Title": "JobsWrapper-Filter",
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    should_close = False
    if session is None:
        session = aiohttp.ClientSession()
        should_close = True

    try:
        async with session.post(
            OPENROUTER_API_URL,
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=60),
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                logger.error(f"OpenRouter API error: {response.status} - {error_text}")
                raise OpenRouterError(f"API request failed with status {response.status}")

            data = await response.json()
            return data["choices"][0]["message"]["content"]

    except aiohttp.ClientError as e:
        logger.error(f"OpenRouter connection error: {e}")
        raise OpenRouterError(f"Connection error: {e}") from e
    except (KeyError, IndexError) as e:
        logger.error(f"OpenRouter response parsing error: {e}")
        raise OpenRouterError(f"Invalid response format: {e}") from e
    finally:
        if should_close:
            await session.close()


async def evaluate_job_async(
    job: Dict,
    search_terms: List[str],
    session: Optional[aiohttp.ClientSession] = None,
) -> Dict:
    """
    Evaluate a single job using OpenRouter API asynchronously.

    Args:
        job: Job dictionary with title, company, location, description
        search_terms: List of target job roles
        session: Optional aiohttp session for connection reuse

    Returns:
        Evaluation result with pass/fail and reasons
    """
    try:
        # Skip jobs with no description
        desc = _safe_str(job.get('description'), '')
        if not desc or len(desc) < 50:
            return {
                "keyword_match": False,
                "visa_sponsorship": False,
                "entry_level": False,
                "requires_phd": False,
                "is_internship": False,
                "reason": "No description available - skipped",
                "skipped": True,
                "job_title": job.get('title', 'Unknown'),
                "company": job.get('company', 'Unknown'),
            }

        prompt = _create_prompt(job, search_terms)

        messages = [
            {"role": "system", "content": "You are a job posting analyzer. Respond only with valid JSON."},
            {"role": "user", "content": prompt}
        ]

        response_text = await _call_openrouter(messages, session=session)
        result = _parse_response(response_text)
        result['job_title'] = job.get('title', 'Unknown')
        result['company'] = job.get('company', 'Unknown')

        return result

    except OpenRouterError as e:
        logger.warning(f"OpenRouter error for {job.get('title', 'Unknown')}: {e}")
        # Default to pass on error
        return {
            "keyword_match": True,
            "visa_sponsorship": True,
            "entry_level": True,
            "requires_phd": False,
            "is_internship": False,
            "reason": f"API error: {str(e)[:50]}",
            "error": True,
            "job_title": job.get('title', 'Unknown'),
            "company": job.get('company', 'Unknown'),
        }
    except Exception as e:
        logger.error(f"Unexpected error evaluating job: {e}")
        return {
            "keyword_match": True,
            "visa_sponsorship": True,
            "entry_level": True,
            "requires_phd": False,
            "is_internship": False,
            "reason": f"Error: {str(e)[:50]}",
            "error": True,
            "job_title": job.get('title', 'Unknown'),
            "company": job.get('company', 'Unknown'),
        }


def should_include_job(evaluation: Dict) -> bool:
    """Determine if job should be included based on evaluation"""
    return (
        evaluation.get("keyword_match", False) and
        evaluation.get("visa_sponsorship", False) and
        evaluation.get("entry_level", False) and
        not evaluation.get("requires_phd", True) and
        not evaluation.get("is_internship", True)
    )


class OpenRouterLLMFilter:
    """Filter jobs using OpenRouter API with async inference"""

    def __init__(self, model: str = OPENROUTER_MODEL, concurrency: int = 20, rate_limit_delay: float = 60):
        """
        Initialize the OpenRouter LLM filter.

        Args:
            model: OpenRouter model identifier
            concurrency: Maximum concurrent API calls
            rate_limit_delay: Delay between requests in seconds (auto-set for free models)
        """
        self.model = model
        # Auto-detect free model and apply rate limiting (20 req/min limit, target 19/min = 3.16s delay)
        self.is_free_model = ":free" in model.lower()
        # if self.is_free_model:
        #     self.concurrency = 1  # Force sequential for free models
        #     self.rate_limit_delay = rate_limit_delay if rate_limit_delay > 0 else 3.2
        # else:
        self.concurrency = concurrency
        self.rate_limit_delay = rate_limit_delay

        if not OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY environment variable not set")

        print(f"🤖 OpenRouter LLM Filter initialized")
        print(f"   Model: {self.model}")
        print(f"   Concurrency: {self.concurrency}")
        if self.is_free_model:
            print(f"   ⚠️  Free model detected - rate limited (~19 req/min)")

    async def evaluate_job(
        self,
        job: Dict,
        search_terms: List[str],
        session: Optional[aiohttp.ClientSession] = None,
    ) -> Dict:
        """Evaluate a single job asynchronously."""
        return await evaluate_job_async(job, search_terms, session)

    async def filter_jobs_async(
        self,
        jobs_list: List[Dict],
        search_terms: List[str],
        verbose: bool = True,
    ) -> List[Dict]:
        """
        Filter jobs using OpenRouter API with async concurrent calls.

        Args:
            jobs_list: List of job dictionaries
            search_terms: Target job roles to match
            verbose: Print progress

        Returns:
            Filtered list of jobs that pass all criteria
        """
        total = len(jobs_list)
        if total == 0:
            return []

        print(f"   🚀 Starting async filtering with concurrency={self.concurrency}...")
        print(f"   📊 Processing {total} jobs...")

        results = []
        idx = 0
        completed = 0
        # Use a single session for all requests (connection pooling)
        async with aiohttp.ClientSession() as session:
            jobs = jobs_list[idx: idx + self.concurrency]

            async with asyncio.TaskGroup() as tg:
                tasks = [(job, tg.create_task(self.evaluate_job(job, search_terms, session))) for job in jobs]
            results = [(job, task_future.result()) for job, task_future in tasks]
            completed += self.concurrency

            if verbose:
                print(f"   🤖 Evaluated {min(completed, total)}/{total}...")
            idx += self.concurrency
            if idx < len(jobs):
                await asyncio.sleep(self.rate_limit_delay)

        # Process results
        filtered = []
        excluded_keyword = 0
        excluded_visa = 0
        excluded_experience = 0
        excluded_phd = 0
        excluded_internship = 0
        skipped = 0

        for job, evaluation in results:
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

            if evaluation.get("is_internship", False):
                excluded_internship += 1
                continue

            # Job passed all filters
            job['llm_evaluation'] = evaluation
            filtered.append(job)

        print(f"   Skipped {skipped} jobs (no description)")
        print(f"   Excluded {excluded_keyword} jobs (keyword mismatch)")
        print(f"   Excluded {excluded_visa} jobs (no visa sponsorship)")
        print(f"   Excluded {excluded_experience} jobs (not entry-level)")
        print(f"   Excluded {excluded_phd} jobs (PhD required)")
        print(f"   Excluded {excluded_internship} jobs (internship)")
        print(f"   ✅ {len(filtered)} jobs passed LLM filter (async)")

        return filtered

    def filter_jobs(
        self,
        jobs_list: List[Dict],
        search_terms: List[str],
        verbose: bool = True,
    ) -> List[Dict]:
        """
        Synchronous wrapper for filter_jobs_async.

        Args:
            jobs_list: List of job dictionaries
            search_terms: Target job roles to match
            verbose: Print progress

        Returns:
            Filtered list of jobs that pass all criteria
        """
        return asyncio.run(self.filter_jobs_async(jobs_list, search_terms, verbose))

    # Alias for backwards compatibility with old LocalLLMFilter interface
    def filter_jobs_parallel(
        self,
        jobs_list: List[Dict],
        search_terms: List[str],
        num_workers: int = 0,
        verbose: bool = True,
    ) -> List[Dict]:
        """
        Backwards-compatible method that uses async filtering.

        Note: num_workers is ignored, concurrency is controlled by self.concurrency
        """
        if num_workers > 0:
            print(f"   ⚠️ num_workers={num_workers} ignored, using async concurrency={self.concurrency}")
        return self.filter_jobs(jobs_list, search_terms, verbose)


# Convenience function for simple usage
async def filter_jobs_async(
    jobs_list: List[Dict],
    search_terms: List[str],
    concurrency: int = 10,
    verbose: bool = True,
) -> List[Dict]:
    """
    Filter jobs using OpenRouter API with async concurrent calls.

    Args:
        jobs_list: List of job dictionaries
        search_terms: Target job roles to match
        concurrency: Maximum concurrent API calls
        verbose: Print progress

    Returns:
        Filtered list of jobs that pass all criteria
    """
    filter_instance = OpenRouterLLMFilter(concurrency=concurrency)
    return await filter_instance.filter_jobs_async(jobs_list, search_terms, verbose)


def filter_jobs(
    jobs_list: List[Dict],
    search_terms: List[str],
    concurrency: int = 10,
    verbose: bool = True,
) -> List[Dict]:
    """
    Synchronous wrapper for filter_jobs_async.

    Args:
        jobs_list: List of job dictionaries
        search_terms: Target job roles to match
        concurrency: Maximum concurrent API calls
        verbose: Print progress

    Returns:
        Filtered list of jobs that pass all criteria
    """
    return asyncio.run(filter_jobs_async(jobs_list, search_terms, concurrency, verbose))


async def main_async():
    """Test the async LLM filter"""
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

    print("🧪 Testing OpenRouter LLM Filter...")

    result = await evaluate_job_async(test_job, search_terms)
    print("\n📊 Evaluation Result:")
    print(json.dumps(result, indent=2))

    print(f"\n✅ Should include: {should_include_job(result)}")


def main():
    """Test the LLM filter (sync wrapper)"""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()


# =============================================================================
# OLD LOCAL INFERENCE LOGIC (PRESERVED - DO NOT DELETE)
# =============================================================================
# The following code is the original implementation using local LLM inference
# with llama_cpp and huggingface_hub. It is preserved here for reference and
# as a fallback option if needed.
#
# To use the old local inference:
# 1. Uncomment the code below
# 2. Install dependencies: pip install huggingface_hub llama-cpp-python
# 3. Use LocalLLMFilter instead of OpenRouterLLMFilter
# =============================================================================

"""
# OLD IMPORTS (for local inference)
# from pathlib import Path
# from huggingface_hub import hf_hub_download
# from llama_cpp import Llama
# import multiprocessing as mp
# from functools import partial
# import psutil

# Global worker state (initialized per process)
_worker_llm: Optional[Llama] = None
_worker_model_path: Optional[str] = None


def _init_worker(model_path: str, n_ctx: int, n_threads: int) -> None:
    '''Initialize LLM model in worker process'''
    global _worker_llm, _worker_model_path
    _worker_model_path = model_path
    print(f"   🔧 Worker {mp.current_process().name} loading model...")
    _worker_llm = Llama(
        model_path=model_path,
        n_ctx=n_ctx,
        n_threads=n_threads,
        n_batch=512,
        verbose=False
    )
    print(f"   ✅ Worker {mp.current_process().name} ready")


def _safe_str_worker(value, default: str = '') -> str:
    '''Safely convert value to string, handling NaN/None (worker version)'''
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    return str(value)


def _create_prompt_worker(job: Dict, search_terms: List[str]) -> str:
    '''Create prompt for job evaluation (worker version)'''
    title = _safe_str_worker(job.get('title'), 'Unknown')
    company = _safe_str_worker(job.get('company'), 'Unknown')
    location = _safe_str_worker(job.get('location'), 'Unknown')
    description = _safe_str_worker(job.get('description'), '')

    search_terms_str = ", ".join(search_terms)

    prompt = f\"\"\"Analyze this job posting and answer with JSON only.

Job Title: {title}
Company: {company}
Location: {location}
Description: {description}

Target Roles: {search_terms_str}

Evaluate:
1. keyword_match: Does the job title/description match any target roles? (true/false)
2. visa_sponsorship: Does it mention H1B, visa sponsorship, or NOT explicitly reject sponsorship? (true/false)
3. entry_level: Is this entry-level (0-1 years experience required or doesn't mention experience at all)? Check for "entry", "junior", "associate", "new grad", or the requireed years of experience is less than/equal to 1.(true/false)
4. requires_phd: Does it require a PhD or doctorate? (true/false)
5. is_internship: Is this an internship position? Look for keywords like "intern", "internship", "co-op", or "summer program". (true/false)

Respond ONLY with valid JSON:
{{"keyword_match": true/false, "visa_sponsorship": true/false, "entry_level": true/false, "requires_phd": true/false, "is_internship": true/false, "reason": "brief explanation"}}\"\"\"

    return prompt


def _parse_response_worker(response_text: str) -> Dict:
    '''Parse LLM response into structured result (worker version)'''
    try:
        start = response_text.find('{')
        end = response_text.rfind('}') + 1

        if start >= 0 and end > start:
            json_str = response_text[start:end]
            result = json.loads(json_str)

            return {
                "keyword_match": result.get("keyword_match", True),
                "visa_sponsorship": result.get("visa_sponsorship", True),
                "entry_level": result.get("entry_level", True),
                "requires_phd": result.get("requires_phd", False),
                "is_internship": result.get("is_internship", False),
                "reason": result.get("reason", "")
            }
        else:
            response_lower = response_text.lower()
            return {
                "keyword_match": "keyword_match\\": true" in response_lower,
                "visa_sponsorship": "visa_sponsorship\\": true" in response_lower,
                "entry_level": "entry_level\\": true" in response_lower,
                "requires_phd": "requires_phd\\": true" in response_lower,
                "is_internship": "is_internship\\": true" in response_lower,
                "reason": "Parsed from text response"
            }

    except json.JSONDecodeError:
        return {
            "keyword_match": True,
            "visa_sponsorship": True,
            "entry_level": True,
            "requires_phd": False,
            "is_internship": False,
            "reason": "JSON parse error - defaulting to pass"
        }


def _evaluate_job_worker(args: Tuple[Dict, List[str]]) -> Dict:
    '''
    Evaluate a single job using the worker's LLM instance.

    Args:
        args: Tuple of (job dict, search_terms list)

    Returns:
        Evaluation result dict with '_job' key containing original job
    '''
    global _worker_llm
    job, search_terms = args

    try:
        desc = _safe_str_worker(job.get('description'), '')
        if not desc or len(desc) < 50:
            return {
                "keyword_match": False,
                "visa_sponsorship": False,
                "entry_level": False,
                "requires_phd": False,
                "is_internship": False,
                "reason": "No description available - skipped",
                "skipped": True,
                "job_title": job.get('title', 'Unknown'),
                "company": job.get('company', 'Unknown'),
                "_job": job
            }

        prompt = _create_prompt_worker(job, search_terms)

        _worker_llm.reset()

        messages = [
            {"role": "system", "content": "You are a job posting analyzer. Respond only with valid JSON."},
            {"role": "user", "content": prompt}
        ]

        response = _worker_llm.create_chat_completion(
            messages=messages,
            max_tokens=256,
            temperature=0.1,
        )

        response_text = response['choices'][0]['message']['content'].strip()
        result = _parse_response_worker(response_text)
        result['job_title'] = job.get('title', 'Unknown')
        result['company'] = job.get('company', 'Unknown')
        result['_job'] = job

        return result

    except Exception as e:
        return {
            "keyword_match": True,
            "visa_sponsorship": True,
            "entry_level": True,
            "requires_phd": False,
            "is_internship": False,
            "reason": f"LLM error: {str(e)[:50]}",
            "error": True,
            "job_title": job.get('title', 'Unknown'),
            "company": job.get('company', 'Unknown'),
            "_job": job
        }


class LocalLLMFilter:
    '''Filter jobs using local LLM inference'''

    MODEL_REPO = "LiquidAI/LFM2.5-1.2B-Instruct-GGUF"
    MODEL_FILE = "LFM2.5-1.2B-Instruct-Q8_0.gguf"

    def __init__(self, model_dir: str = "models"):
        '''
        Initialize the local LLM filter

        Args:
            model_dir: Directory to store downloaded models
        '''
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
        '''Download the GGUF model from HuggingFace'''
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
        '''Load the GGUF model with llama.cpp'''
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
        '''Safely convert value to string, handling NaN/None'''
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return default
        return str(value)

    def _create_prompt(self, job: Dict, search_terms: List[str]) -> str:
        '''Create prompt for job evaluation'''
        title = self._safe_str(job.get('title'), 'Unknown')
        company = self._safe_str(job.get('company'), 'Unknown')
        location = self._safe_str(job.get('location'), 'Unknown')
        description = self._safe_str(job.get('description'), '')
        search_terms_str = ", ".join(search_terms)

        prompt = f\"\"\"Analyze this job posting and answer with JSON only.

Job Title: {title}
Company: {company}
Location: {location}
Description: {description}

Target Roles: {search_terms_str}

Evaluate:
1. keyword_match: Does the job title/description match any target roles? That is, does one of the target roles, which are separated by a comma, exist in the job title/description? (true/false)
2. visa_sponsorship: Does it mention H1B, visa sponsorship, or NOT explicitly reject sponsorship? (true/false)
3. entry_level: Is this entry-level (0-3 years experience required)? keywords including "entry", "junior", "associate", "new grad", or "0-3 years of experience" should be true. keywords like
    senior, mid-level, Sr., staff, principal should be considered false. (true/false)
4. requires_phd: Does it require a PhD or doctorate? (true/false)
5. is_internship: Is this an internship position? Look for keywords like "intern", "internship", "co-op", or "summer program". (true/false)

Respond ONLY with valid JSON:
{{"keyword_match": true/false, "visa_sponsorship": true/false, "entry_level": true/false, "requires_phd": true/false, "is_internship": true/false, "reason": "brief explanation"}}\"\"\"

        return prompt

    def evaluate_job(self, job: Dict, search_terms: List[str], _retry: bool = True) -> Dict:
        '''
        Evaluate a single job using local LLM

        Args:
            job: Job dictionary
            search_terms: List of target job roles
            _retry: Internal flag for retry with truncation

        Returns:
            Evaluation result with pass/fail and reasons
        '''
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
                    "is_internship": False,
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
                "is_internship": False,
                "reason": f"LLM error: {str(e)[:50]}",
                "error": True
            }

    def _parse_response(self, response_text: str) -> Dict:
        '''Parse LLM response into structured result'''
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
                    "is_internship": result.get("is_internship", False),
                    "reason": result.get("reason", "")
                }
            else:
                # Fallback parsing
                response_lower = response_text.lower()
                return {
                    "keyword_match": "keyword_match\\": true" in response_lower or "keyword_match\\":true" in response_lower,
                    "visa_sponsorship": "visa_sponsorship\\": true" in response_lower or "no sponsor" not in response_lower,
                    "entry_level": "entry_level\\": true" in response_lower,
                    "requires_phd": "requires_phd\\": true" in response_lower,
                    "is_internship": "is_internship\\": true" in response_lower,
                    "reason": "Parsed from text response"
                }

        except json.JSONDecodeError:
            # Default to permissive on parse error
            return {
                "keyword_match": True,
                "visa_sponsorship": True,
                "entry_level": True,
                "requires_phd": False,
                "is_internship": False,
                "reason": "JSON parse error - defaulting to pass"
            }

    def should_include_job(self, evaluation: Dict) -> bool:
        '''Determine if job should be included based on evaluation'''
        return (
            evaluation.get("keyword_match", False) and
            evaluation.get("visa_sponsorship", False) and
            evaluation.get("entry_level", False) and
            not evaluation.get("requires_phd", True) and
            not evaluation.get("is_internship", True)
        )

    def filter_jobs(
        self,
        jobs_list: List[Dict],
        search_terms: List[str],
        verbose: bool = True
    ) -> List[Dict]:
        '''
        Filter jobs using local LLM

        Args:
            jobs_list: List of job dictionaries
            search_terms: Target job roles to match
            verbose: Print progress

        Returns:
            Filtered list of jobs that pass all criteria
        '''
        filtered = []
        excluded_keyword = 0
        excluded_visa = 0
        excluded_experience = 0
        excluded_phd = 0
        excluded_internship = 0
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

            if evaluation.get("is_internship", False):
                excluded_internship += 1
                continue

            # Job passed all filters
            job['llm_evaluation'] = evaluation
            filtered.append(job)

        print(f"   Skipped {skipped} jobs (no description)")
        print(f"   Excluded {excluded_keyword} jobs (keyword mismatch)")
        print(f"   Excluded {excluded_visa} jobs (no visa sponsorship)")
        print(f"   Excluded {excluded_experience} jobs (not entry-level)")
        print(f"   Excluded {excluded_phd} jobs (PhD required)")
        print(f"   Excluded {excluded_internship} jobs (internship)")
        print(f"   ✅ {len(filtered)} jobs passed LLM filter")

        return filtered

    def _calculate_optimal_workers(self, requested_workers: int) -> int:
        '''
        Calculate optimal number of workers based on available system RAM.

        Each model instance uses approximately 1.5-2GB RAM for this 1.2B model.
        We reserve 2GB for system overhead and other processes.

        Args:
            requested_workers: User-requested number of workers

        Returns:
            Optimal number of workers based on available RAM
        '''
        try:
            mem = psutil.virtual_memory()
            available_gb = mem.available / (1024 ** 3)
            total_gb = mem.total / (1024 ** 3)

            # Each worker needs ~2GB (model + overhead), reserve 2GB for system
            ram_per_worker = 2.0
            system_reserve = 2.0

            usable_ram = available_gb - system_reserve
            max_workers_by_ram = max(1, int(usable_ram / ram_per_worker))

            # Also limit by CPU cores
            max_workers_by_cpu = max(1, mp.cpu_count() // 2)

            optimal = min(requested_workers, max_workers_by_ram, max_workers_by_cpu)

            print(f"   💾 RAM: {available_gb:.1f}GB available / {total_gb:.1f}GB total")
            print(f"   🔢 Workers: requested={requested_workers}, max_by_ram={max_workers_by_ram}, max_by_cpu={max_workers_by_cpu}")
            print(f"   ✅ Using {optimal} worker(s)")

            return optimal

        except Exception as e:
            print(f"   ⚠️ Could not detect RAM: {e}, using 1 worker")
            return 1

    def filter_jobs_parallel(
        self,
        jobs_list: List[Dict],
        search_terms: List[str],
        num_workers: int = 0,
        verbose: bool = True
    ) -> List[Dict]:
        '''
        Filter jobs using multiple LLM instances in parallel.

        Each worker process loads its own model instance for true parallelism.

        Args:
            jobs_list: List of job dictionaries
            search_terms: Target job roles to match
            num_workers: Number of workers (0 = auto-detect based on RAM)
            verbose: Print progress

        Returns:
            Filtered list of jobs that pass all criteria
        '''
        total = len(jobs_list)
        if total == 0:
            return []

        # Auto-detect or validate worker count based on system RAM
        if num_workers <= 0:
            num_workers = self._calculate_optimal_workers(4)  # Default max 4
        else:
            num_workers = self._calculate_optimal_workers(num_workers)

        # For small job lists or single worker, use sequential processing
        if total < num_workers * 2 or num_workers == 1:
            print(f"   📝 Using sequential processing (jobs={total}, workers={num_workers})...")
            return self.filter_jobs(jobs_list, search_terms, verbose)

        print(f"   🚀 Starting parallel processing with {num_workers} workers...")
        print(f"   📊 Processing {total} jobs...")

        # Prepare args for workers: list of (job, search_terms) tuples
        work_items = [(job, search_terms) for job in jobs_list]

        # Calculate threads per worker (divide available threads)
        total_threads = 8
        threads_per_worker = max(2, total_threads // num_workers)

        # Create process pool with model initialization
        try:
            with mp.Pool(
                processes=num_workers,
                initializer=_init_worker,
                initargs=(str(self.model_path), 8192, threads_per_worker)
            ) as pool:
                # Process jobs in parallel
                results = pool.map(_evaluate_job_worker, work_items)
        except Exception as e:
            print(f"   ❌ Parallel processing failed: {e}")
            print(f"   🔄 Falling back to sequential processing...")
            return self.filter_jobs(jobs_list, search_terms, verbose)

        # Process results
        filtered = []
        excluded_keyword = 0
        excluded_visa = 0
        excluded_experience = 0
        excluded_phd = 0
        excluded_internship = 0
        skipped = 0

        for evaluation in results:
            job = evaluation.pop('_job', None)
            if job is None:
                continue

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

            if evaluation.get("is_internship", False):
                excluded_internship += 1
                continue

            job['llm_evaluation'] = evaluation
            filtered.append(job)

        print(f"   Skipped {skipped} jobs (no description)")
        print(f"   Excluded {excluded_keyword} jobs (keyword mismatch)")
        print(f"   Excluded {excluded_visa} jobs (no visa sponsorship)")
        print(f"   Excluded {excluded_experience} jobs (not entry-level)")
        print(f"   Excluded {excluded_phd} jobs (PhD required)")
        print(f"   Excluded {excluded_internship} jobs (internship)")
        print(f"   ✅ {len(filtered)} jobs passed LLM filter (parallel)")

        return filtered
"""
