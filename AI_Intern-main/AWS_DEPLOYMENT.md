# AWS EC2 Deployment Guide for DDQ Scorer

## Overview

This guide walks you through deploying the AI_Intern DDQ (Due Diligence Questionnaire) scorer on AWS EC2 to run automatically every 3 days.

## Prerequisites

1. AWS EC2 instance (Ubuntu 20.04+ recommended)
2. Python 3.8+ installed
3. Git installed
4. Environment variables configured (from root project)

## Deployment Steps

### 1. Clone and Setup

```bash
# Clone the repository (if not already done)
git clone <your-repo-url>
cd Research_Intern_latest

# Navigate to AI_Intern-main
cd AI_Intern-main

# Verify required files exist
ls -la run_ddq_scorer.sh install_cron.sh
```

### 2. Environment Setup

```bash
# Install Python virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
pip install -r ../requirements.txt
```

### 3. Configure Environment Variables

Ensure your root directory (Research_Intern_latest) has a `.env` file with:

```bash
# Required environment variables
NOTION_TOKEN=your_notion_token
OPENAI_API_KEY=your_openai_api_key
FIRECRAWL_API_KEY=your_firecrawl_api_key
# ... other required variables
```

### 4. Test the Setup

```bash
# Test configuration
python3 -c "from src.config import check_required_env; check_required_env(); print('✓ All good!')"

# Test the cron script (dry run)
./run_ddq_scorer.sh
```

### 5. Install Cron Job

```bash
# Install the automated cron job
./install_cron.sh
```

This will:
- Set up a cron job to run every 3 days at midnight
- Create logging infrastructure
- Provide monitoring commands

## Monitoring and Maintenance

### Check Cron Job Status

```bash
# View installed cron jobs
crontab -l

# Check if cron service is running
sudo systemctl status cron
```

### View Logs

```bash
# Real-time log monitoring
tail -f logs/cron_ddq_scorer.log

# View recent log entries
tail -100 logs/cron_ddq_scorer.log

# View all logs
less logs/cron_ddq_scorer.log
```

### Manual Execution

```bash
# Run the DDQ scorer manually
cd AI_Intern-main
source venv/bin/activate
python3 run.py
```

## EC2 Specific Considerations

### Security Groups

Ensure your EC2 security group allows:
- SSH access (port 22) for administration
- HTTPS outbound (port 443) for API calls

### Instance Persistence

- Use an Elastic IP if you need consistent external IP
- Consider using EBS snapshots for backup
- Set up CloudWatch monitoring for instance health

### Performance

- Minimum recommended: t3.medium instance
- Storage: At least 20GB for logs and temporary files
- Memory: 4GB+ recommended for processing

## Troubleshooting

### Common Issues

1. **Permission Denied**
   ```bash
   chmod +x run_ddq_scorer.sh install_cron.sh
   ```

2. **Environment Variables Not Found**
   ```bash
   # Check if .env file exists in root
   ls -la ../env
   # Verify environment variables are loaded
   python3 -c "from src.config import check_required_env; check_required_env()"
   ```

3. **Cron Job Not Running**
   ```bash
   # Check cron service
   sudo systemctl status cron
   # Check system logs
   sudo journalctl -u cron
   ```

4. **Virtual Environment Issues**
   ```bash
   # Recreate virtual environment
   rm -rf venv
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt -r ../requirements.txt
   ```

## File Structure

```
AI_Intern-main/
├── run_ddq_scorer.sh      # Main cron script
├── install_cron.sh        # Cron installation script
├── venv/                  # Python virtual environment
├── logs/                  # Log files directory
├── src/                   # Core DDQ modules
├── run.py                 # Main orchestrator
├── requirements.txt       # Dependencies
└── AWS_DEPLOYMENT.md      # This file
```

## Maintenance Schedule

- **Weekly**: Check logs for errors
- **Monthly**: Review EC2 instance performance
- **Quarterly**: Update dependencies and security patches

## Support

For issues or questions:
1. Check the logs first: `tail -f logs/cron_ddq_scorer.log`
2. Verify environment setup: `python3 -c "from src.config import check_required_env; check_required_env()"`
3. Test manual execution: `./run_ddq_scorer.sh` 