"""
Email sender using Resend API
Sends daily job digest with HTML formatting
"""
import os
from typing import List, Dict, Optional
from datetime import datetime
import resend
from dotenv import load_dotenv

load_dotenv()


class EmailSender:
    """Email dispatcher using Resend service"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Resend client
        
        Args:
            api_key: Resend API key (defaults to env var)
        """
        self.api_key = api_key or os.getenv("RESEND_API_KEY")
        
        if not self.api_key:
            raise ValueError("RESEND_API_KEY not found in environment")
        
        resend.api_key = self.api_key
        self.from_email = "Job Hunter <onboarding@resend.dev>"  # Resend test domain
        self.recipient = os.getenv("RECIPIENT_EMAIL")
        
        if not self.recipient:
            raise ValueError("RECIPIENT_EMAIL not found in environment")
    
    def create_job_html(self, job: Dict) -> str:
        """
        Generate HTML for a single job listing
        
        Args:
            job: Job dict with analysis results
            
        Returns:
            HTML string
        """
        job_data = job.get('job_data', job)
        
        title = job_data.get('title', 'Unknown Position')
        company = job_data.get('company', 'Unknown Company')
        location = job_data.get('location', 'Unknown Location')
        job_url = job_data.get('job_url', '#')
        site = job_data.get('site', 'Unknown')
        score = job.get('score', 0)
        summary = job.get('summary', '无推荐理由')
        
        # Score color coding
        if score >= 8:
            score_color = "#22c55e"  # Green
            score_label = "强烈推荐"
        elif score >= 6:
            score_color = "#3b82f6"  # Blue
            score_label = "推荐"
        else:
            score_color = "#94a3b8"  # Gray
            score_label = "一般"
        
        return f"""
        <div style="border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin-bottom: 20px; background-color: #ffffff;">
            <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px;">
                <h2 style="margin: 0; font-size: 20px; color: #1e293b;">
                    <a href="{job_url}" style="color: #2563eb; text-decoration: none;">{title}</a>
                </h2>
                <div style="background-color: {score_color}; color: white; padding: 4px 12px; border-radius: 4px; font-weight: bold; font-size: 14px; white-space: nowrap;">
                    {score}/10 {score_label}
                </div>
            </div>
            
            <div style="color: #64748b; font-size: 14px; margin-bottom: 8px;">
                <span style="font-weight: 600; color: #475569;">📍 {company}</span> · {location}
            </div>
            
            <div style="color: #94a3b8; font-size: 12px; margin-bottom: 12px;">
                来源: {site.upper()}
            </div>
            
            <div style="background-color: #f8fafc; padding: 12px; border-radius: 6px; border-left: 3px solid {score_color};">
                <p style="margin: 0; color: #334155; font-size: 14px; line-height: 1.6;">
                    💡 <strong>AI 推荐理由：</strong>{summary}
                </p>
            </div>
            
            <div style="margin-top: 12px;">
                <a href="{job_url}" style="display: inline-block; background-color: #2563eb; color: white; padding: 8px 16px; border-radius: 6px; text-decoration: none; font-size: 14px; font-weight: 500;">
                    查看详情 →
                </a>
            </div>
        </div>
        """
    
    def create_email_body(self, jobs: List[Dict], date: str) -> str:
        """
        Create full HTML email body
        
        Args:
            jobs: List of analyzed jobs
            date: Date string for email title
            
        Returns:
            Complete HTML email
        """
        # Header
        html = f"""
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Job Hunter Daily Digest</title>
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f1f5f9; margin: 0; padding: 20px;">
            <div style="max-width: 800px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                
                <!-- Header -->
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; text-align: center;">
                    <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 700;">
                        🎯 Job Hunter Sentinel
                    </h1>
                    <p style="color: #e0e7ff; margin: 8px 0 0 0; font-size: 16px;">
                        您的每日职位精选 · {date}
                    </p>
                </div>
                
                <!-- Summary -->
                <div style="padding: 20px; background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <p style="margin: 0; color: #475569; font-size: 16px;">
                        今日为您精选 <strong style="color: #2563eb; font-size: 20px;">{len(jobs)}</strong> 个高匹配度职位
                    </p>
                </div>
                
                <!-- Job Listings -->
                <div style="padding: 20px;">
        """
        
        # Add each job
        for job in jobs:
            html += self.create_job_html(job)
        
        # Footer
        html += """
                </div>
                
                <!-- Footer -->
                <div style="padding: 20px; background-color: #f8fafc; border-top: 1px solid #e2e8f0; text-align: center;">
                    <p style="margin: 0 0 8px 0; color: #64748b; font-size: 14px;">
                        由 Job Hunter Sentinel 自动生成
                    </p>
                    <p style="margin: 0; color: #94a3b8; font-size: 12px;">
                        使用 Python JobSpy + Gemini AI + Resend 构建
                    </p>
                </div>
                
            </div>
        </body>
        </html>
        """
        
        return html
    
    def send_daily_digest(
        self,
        jobs: List[Dict],
        custom_subject: Optional[str] = None
    ) -> bool:
        """
        Send daily job digest email
        
        Args:
            jobs: List of analyzed jobs to send
            custom_subject: Optional custom email subject
            
        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            if not jobs:
                print("⚠️ No jobs to send, skipping email")
                return False
            
            # Get current date
            today = datetime.now().strftime("%Y年%m月%d日")
            
            # Create email content
            html_body = self.create_email_body(jobs, today)
            
            # Default subject
            subject = custom_subject or f"🎯 Job Hunter Daily Digest - {len(jobs)} 个职位推荐 ({today})"
            
            # Send via Resend
            print(f"📧 Sending email to {self.recipient}...")
            
            params = {
                "from": self.from_email,
                "to": [self.recipient],
                "subject": subject,
                "html": html_body
            }
            
            response = resend.Emails.send(params)
            
            print(f"✅ Email sent successfully! ID: {response.get('id', 'N/A')}")
            return True
            
        except Exception as e:
            print(f"❌ Email sending failed: {e}")
            return False
    
    def send_empty_notification(self) -> bool:
        """
        Send a notification when no jobs are found
        
        Returns:
            True if successful
        """
        try:
            today = datetime.now().strftime("%Y年%m月%d日")
            
            html_body = f"""
            <!DOCTYPE html>
            <html lang="zh-CN">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f1f5f9; padding: 20px;">
                <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; padding: 30px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                    <h1 style="color: #64748b; margin: 0 0 16px 0; font-size: 24px;">
                        📭 Job Hunter Sentinel
                    </h1>
                    <p style="color: #475569; font-size: 16px; line-height: 1.6;">
                        今日（{today}）未发现符合条件的新职位。
                    </p>
                    <p style="color: #94a3b8; font-size: 14px; margin-top: 20px;">
                        系统将继续监控，有新职位时会立即通知您。
                    </p>
                </div>
            </body>
            </html>
            """
            
            params = {
                "from": self.from_email,
                "to": [self.recipient],
                "subject": f"📭 Job Hunter - 今日无新职位 ({today})",
                "html": html_body
            }
            
            response = resend.Emails.send(params)
            print(f"📭 Empty notification sent. ID: {response.get('id', 'N/A')}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to send empty notification: {e}")
            return False


def main():
    """Test email sending"""
    sender = EmailSender()
    
    # Test jobs
    test_jobs = [
        {
            "score": 9,
            "summary": "顶级科技公司，明确支持 O-1 签证，涉及前沿 AI 技术，职位要求高级技术专家，非常适合杰出人才申请。",
            "job_data": {
                "title": "Senior ML Engineer",
                "company": "Google",
                "location": "Mountain View, CA",
                "job_url": "https://example.com/job/1",
                "site": "linkedin"
            }
        },
        {
            "score": 7,
            "summary": "知名创业公司，技术栈先进，虽然签证支持未明确，但公司规模和技术挑战度较高，值得尝试。",
            "job_data": {
                "title": "Full Stack Engineer",
                "company": "OpenAI",
                "location": "San Francisco, CA",
                "job_url": "https://example.com/job/2",
                "site": "indeed"
            }
        }
    ]
    
    # Send test email
    sender.send_daily_digest(test_jobs)
    
    # Test empty notification
    # sender.send_empty_notification()


if __name__ == "__main__":
    main()
