import requests
import time
import logging
from datetime import datetime
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
        self.headers = {
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}',
            'Content-Type': 'application/json'
        }
    
    def send_telegram_alert(self, message: str, severity: str = "ERROR"):
        """Send alert message to Telegram bot"""
        try:
            emoji = "🚨" if severity == "ERROR" else "⚠️" if severity == "WARNING" else "ℹ️"
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
                # Check main API health
                health_status = self.check_supabase_health()
                
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