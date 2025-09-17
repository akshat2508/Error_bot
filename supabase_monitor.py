import requests
import time
import logging
from datetime import datetime, time as dt_time
import json
import sys
from typing import Dict, Any
from dotenv import load_dotenv
import os
load_dotenv() 


SUPABASE_URL =   os.getenv("SUPABASE_URL")
SUPABASE_KEY =  os.getenv("SUPABASE_KEY")
TELEGRAM_BOT_TOKEN =  os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID =  os.getenv("TELEGRAM_CHAT_ID")

# Monitoring configuration
CHECK_INTERVAL = 60  # Check every 60 seconds
MAX_RETRIES = 3
REQUEST_TIMEOUT = 10

# Daily report configuration
DAILY_REPORT_TIME = dt_time(9, 0)  # Send daily report at 9:00 AM (24-hour format)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('supabase_monitor.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

class SupabaseMonitor:
    def __init__(self):
        self.last_status = None
        self.consecutive_failures = 0
        self.last_daily_report_date = None
        self.daily_stats = {
            'checks_today': 0,
            'errors_today': 0,
            'warnings_today': 0,
            'total_downtime_minutes': 0,
            'average_response_time': 0,
            'response_times': []
        }
        self.headers = {
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}',
            'Content-Type': 'application/json'
        }
    
    def reset_daily_stats(self):
        """Reset daily statistics for a new day"""
        self.daily_stats = {
            'checks_today': 0,
            'errors_today': 0,
            'warnings_today': 0,
            'total_downtime_minutes': 0,
            'average_response_time': 0,
            'response_times': []
        }
    
    def update_daily_stats(self, health_status):
        """Update daily statistics"""
        self.daily_stats['checks_today'] += 1
        
        if health_status['status'] == 'error':
            self.daily_stats['errors_today'] += 1
            self.daily_stats['total_downtime_minutes'] += CHECK_INTERVAL / 60
        elif health_status['status'] == 'warning':
            self.daily_stats['warnings_today'] += 1
        
        if health_status.get('response_time'):
            self.daily_stats['response_times'].append(health_status['response_time'])
            self.daily_stats['average_response_time'] = sum(self.daily_stats['response_times']) / len(self.daily_stats['response_times'])
    
    def should_send_daily_report(self) -> bool:
        """Check if it's time to send the daily report"""
        now = datetime.now()
        current_date = now.date()
        current_time = now.time()
        
        # Check if it's a new day and we haven't sent today's report yet
        if (self.last_daily_report_date != current_date and 
            current_time >= DAILY_REPORT_TIME):
            return True
        return False
    
    def send_telegram_alert(self, message: str, severity: str = "ERROR"):
        """Send alert message to Telegram bot"""
        try:
            emoji = "🚨" if severity == "ERROR" else "⚠️" if severity == "WARNING" else "ℹ️"
            if severity == "DAILY_SUCCESS":
                emoji = "✅"
            
            formatted_message = f"{emoji} *Supabase Monitor Alert*\n\n"
            formatted_message += f"*Severity:* {severity}\n"
            formatted_message += f"*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            formatted_message += f"*Details:*\n{message}"
            
            telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                'chat_id': TELEGRAM_CHAT_ID,
                'text': formatted_message,
                'parse_mode': 'Markdown'
            }
            
            response = requests.post(telegram_url, json=payload, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            logging.info(f"Telegram alert sent successfully: {severity}")
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to send Telegram alert: {str(e)}")
        except Exception as e:
            logging.error(f"Unexpected error sending Telegram alert: {str(e)}")
    
    def send_daily_success_report(self):
        """Send daily success report with statistics"""
        uptime_percentage = 100 - (self.daily_stats['errors_today'] / max(self.daily_stats['checks_today'], 1) * 100)
        
        message = f"🌅 *Daily Supabase Status Report*\n\n"
        message += f"*Date:* {datetime.now().strftime('%Y-%m-%d')}\n"
        message += f"*Overall Status:* {'🟢 HEALTHY' if self.last_status == 'healthy' else '🔴 ISSUES DETECTED'}\n\n"
        
        message += f"*24-Hour Statistics:*\n"
        message += f"• Health checks performed: {self.daily_stats['checks_today']}\n"
        message += f"• Uptime: {uptime_percentage:.1f}%\n"
        message += f"• Errors detected: {self.daily_stats['errors_today']}\n"
        message += f"• Warnings: {self.daily_stats['warnings_today']}\n"
        
        if self.daily_stats['total_downtime_minutes'] > 0:
            message += f"• Total downtime: {self.daily_stats['total_downtime_minutes']:.1f} minutes\n"
        
        if self.daily_stats['average_response_time'] > 0:
            message += f"• Average response time: {self.daily_stats['average_response_time']:.1f}ms\n"
        
        message += f"\n*Current Status:* All systems operational ✅"
        
        self.send_telegram_alert(message, "DAILY_SUCCESS")
        self.last_daily_report_date = datetime.now().date()
        
        # Reset daily stats for the new day
        self.reset_daily_stats()
    
    def check_supabase_health(self) -> Dict[str, Any]:
        """Check Supabase API health by making a simple query"""
        health_status = {
            'status': 'unknown',
            'response_time': None,
            'error_message': None,
            'status_code': None
        }
        
        try:
            start_time = time.time()
            
            # Test basic connectivity with a simple REST API call
            # This tries to query a table (you can modify the endpoint as needed)
            test_url = f"{SUPABASE_URL}/rest/v1/"
            
            response = requests.get(
                test_url,
                headers=self.headers,
                timeout=REQUEST_TIMEOUT
            )
            
            response_time = time.time() - start_time
            health_status['response_time'] = round(response_time * 1000, 2)  # Convert to milliseconds
            health_status['status_code'] = response.status_code
            
            # Check for various error conditions
            if response.status_code == 200:
                health_status['status'] = 'healthy'
            elif response.status_code >= 500:
                health_status['status'] = 'error'
                health_status['error_message'] = f"Internal server error: {response.status_code}"
            elif response.status_code == 401:
                health_status['status'] = 'error'
                health_status['error_message'] = "Authentication failed - check your API key"
            elif response.status_code == 403:
                health_status['status'] = 'error'
                health_status['error_message'] = "Access forbidden - check permissions"
            elif response.status_code >= 400:
                health_status['status'] = 'warning'
                health_status['error_message'] = f"Client error: {response.status_code}"
            else:
                health_status['status'] = 'warning'
                health_status['error_message'] = f"Unexpected status code: {response.status_code}"
                
        except requests.exceptions.Timeout:
            health_status['status'] = 'error'
            health_status['error_message'] = f"Request timeout after {REQUEST_TIMEOUT} seconds"
            
        except requests.exceptions.ConnectionError:
            health_status['status'] = 'error'
            health_status['error_message'] = "Connection error - unable to reach Supabase"
            
        except requests.exceptions.RequestException as e:
            health_status['status'] = 'error'
            health_status['error_message'] = f"Request error: {str(e)}"
            
        except Exception as e:
            health_status['status'] = 'error'
            health_status['error_message'] = f"Unexpected error: {str(e)}"
        
        return health_status
    
    def check_specific_endpoints(self) -> Dict[str, Any]:
        """Check specific Supabase endpoints for more detailed monitoring"""
        endpoints_status = {}
        
        # List of endpoints to check (modify based on your needs)
        endpoints = [
            {'name': 'Auth', 'url': f"{SUPABASE_URL}/auth/v1/health"},
            {'name': 'Realtime', 'url': f"{SUPABASE_URL}/realtime/v1/health"},
            {'name': 'Storage', 'url': f"{SUPABASE_URL}/storage/v1/health"},
        ]
        
        for endpoint in endpoints:
            try:
                response = requests.get(
                    endpoint['url'],
                    headers=self.headers,
                    timeout=REQUEST_TIMEOUT
                )
                
                endpoints_status[endpoint['name']] = {
                    'status': 'healthy' if response.status_code == 200 else 'error',
                    'status_code': response.status_code,
                    'error': None if response.status_code == 200 else f"HTTP {response.status_code}"
                }
                
            except Exception as e:
                endpoints_status[endpoint['name']] = {
                    'status': 'error',
                    'status_code': None,
                    'error': str(e)
                }
        
        return endpoints_status
    
    def monitor_loop(self):
        """Main monitoring loop"""
        logging.info("Starting Supabase monitoring...")
        self.send_telegram_alert("Supabase monitoring started successfully!", "INFO")
        
        while True:
            try:
                # Check if it's time to send daily report
                if self.should_send_daily_report() and self.last_status == 'healthy':
                    self.send_daily_success_report()
                
                # Check main API health
                health_status = self.check_supabase_health()
                
                # Update daily statistics
                self.update_daily_stats(health_status)
                
                # Check specific endpoints
                endpoints_status = self.check_specific_endpoints()
                
                current_status = health_status['status']
                
                # Alert logic
                if current_status == 'error':
                    self.consecutive_failures += 1
                    
                    # Send alert on first failure or every 5th consecutive failure
                    if self.consecutive_failures == 1 or self.consecutive_failures % 5 == 0:
                        message = f"Supabase API is DOWN!\n\n"
                        message += f"Error: {health_status['error_message']}\n"
                        message += f"Status Code: {health_status.get('status_code', 'N/A')}\n"
                        message += f"Consecutive failures: {self.consecutive_failures}\n\n"
                        
                        # Add endpoint details if available
                        failed_endpoints = [name for name, status in endpoints_status.items() 
                                          if status['status'] == 'error']
                        if failed_endpoints:
                            message += f"Failed endpoints: {', '.join(failed_endpoints)}"
                        
                        self.send_telegram_alert(message, "ERROR")
                    
                elif current_status == 'warning':
                    message = f"Supabase API Warning!\n\n"
                    message += f"Issue: {health_status['error_message']}\n"
                    message += f"Status Code: {health_status.get('status_code', 'N/A')}\n"
                    message += f"Response Time: {health_status.get('response_time', 'N/A')}ms"
                    
                    self.send_telegram_alert(message, "WARNING")
                    self.consecutive_failures = 0
                    
                else:  # healthy
                    # Send recovery alert if we were previously failing
                    if self.last_status in ['error', 'warning'] and current_status == 'healthy':
                        message = f"Supabase API is back online! ✅\n\n"
                        message += f"Response Time: {health_status.get('response_time', 'N/A')}ms\n"
                        message += f"Previous consecutive failures: {self.consecutive_failures}"
                        
                        self.send_telegram_alert(message, "INFO")
                    
                    self.consecutive_failures = 0
                
                self.last_status = current_status
                
                # Log current status
                log_message = f"Status: {current_status}"
                if health_status.get('response_time'):
                    log_message += f", Response time: {health_status['response_time']}ms"
                if health_status.get('error_message'):
                    log_message += f", Error: {health_status['error_message']}"
                
                logging.info(log_message)
                
                # Sleep before next check
                time.sleep(CHECK_INTERVAL)
                
            except KeyboardInterrupt:
                logging.info("Monitoring stopped by user")
                self.send_telegram_alert("Supabase monitoring stopped by user", "INFO")
                break
                
            except Exception as e:
                logging.error(f"Unexpected error in monitoring loop: {str(e)}")
                self.send_telegram_alert(f"Monitor error: {str(e)}", "ERROR")
                time.sleep(CHECK_INTERVAL)

def validate_config():
    """Validate configuration before starting monitoring"""
    errors = []
    
    if not SUPABASE_URL or SUPABASE_URL == "your_supabase_url_here":
        errors.append("SUPABASE_URL is not configured")
    
    if not SUPABASE_KEY or SUPABASE_KEY == "your_supabase_anon_key_here":
        errors.append("SUPABASE_KEY is not configured")
    
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "your_telegram_bot_token_here":
        errors.append("TELEGRAM_BOT_TOKEN is not configured")
    
    if not TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID == "your_telegram_chat_id_here":
        errors.append("TELEGRAM_CHAT_ID is not configured")
    
    if errors:
        print("Configuration errors found:")
        for error in errors:
            print(f"- {error}")
        sys.exit(1)

if __name__ == "__main__":
    # Validate configuration
    validate_config()
    
    # Create and start monitor
    monitor = SupabaseMonitor()
    monitor.monitor_loop()