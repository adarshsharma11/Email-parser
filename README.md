# Vacation Rental Booking Automation

A production-ready Python system that automatically extracts vacation rental booking data from Gmail inboxes and syncs it to Supabase (Postgres). The system supports multiple platforms including Vrbo, Airbnb, and Booking.com.

## Features

- **Email Reader**: Connects to Gmail via IMAP to fetch booking confirmation emails
- **Booking Parser**: Extracts structured data from emails using HTML parsing and regex
- **Supabase Sync**: Uploads bookings to Supabase with duplicate detection
- **CLI Interface**: Command-line tool with various options for processing
- **Comprehensive Logging**: Colorized logging with detailed processing summaries
- **Testing**: Full unit test coverage with mocks for external services

## Architecture

The system is built with a modular architecture:

```
src/
├── email_reader/          # Gmail IMAP client
├── booking_parser/        # Email parsing and data extraction
├── supabase_sync/         # Supabase integration
├── utils/                 # Shared utilities, models, and logging
└── main.py               # Main orchestrator and CLI

config/
├── settings.py           # Configuration management

tests/                    # Unit tests for all components
```

## Prerequisites

- Python 3.8+
- Gmail account with IMAP enabled
- Supabase project and API keys

## Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd vacation_rental_automation
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

## Configuration

### Gmail Setup

1. Enable IMAP in your Gmail account settings
2. Create an App Password (recommended) or use your regular password
3. Add credentials to `.env`:
   ```
   GMAIL_EMAIL=your-email@gmail.com
   GMAIL_PASSWORD=your-app-password
   ```

### Supabase Setup

1. Create a project at https://supabase.com/
2. In Project Settings > API, copy:
   - Project URL (SUPABASE_URL)
   - anon key (SUPABASE_ANON_KEY)
   - service_role key (SUPABASE_SERVICE_ROLE_KEY) – keep this secret
3. Create a table `bookings` with (recommended) columns:
   - reservation_id (text, primary key)
   - platform (text)
   - guest_name (text)
   - guest_phone (text, nullable)
   - guest_email (text, nullable)
   - check_in_date (timestamptz, nullable)
   - check_out_date (timestamptz, nullable)
   - property_id (text, nullable)
   - property_name (text, nullable)
   - number_of_guests (int4, nullable)
   - total_amount (float8, nullable)
   - currency (text, nullable)
   - booking_date (timestamptz, nullable)
   - email_id (text, nullable)
   - created_at (timestamptz, default now())
   - updated_at (timestamptz, default now())
   - raw_data (jsonb, nullable)
4. Configure RLS policies. For development, you can disable RLS or allow the service role full access.
5. Add Supabase credentials to `.env`:
   ```
   SUPABASE_URL=https://your-project-id.supabase.co
   SUPABASE_ANON_KEY=...
   SUPABASE_SERVICE_ROLE_KEY=...
   ```

## Usage

### Basic Usage

Process all booking emails from the last 7 days:
```bash
python run.py
```

### Command Line Options

```bash
# Process specific platform
python run.py --platform vrbo

# Look back specific number of days
python run.py --since-days 30

# Limit number of emails to process
python run.py --limit 50

# Dry run (don't sync to Supabase)
python run.py --dry-run

# Show booking statistics
python run.py --stats

# Set log level
python run.py --log-level DEBUG

# Save logs to file
python run.py --log-file logs/processing.log
```

### Examples

**Process only Airbnb bookings from the last 14 days:**
```bash
python run.py --platform airbnb --since-days 14
```

**Dry run to test parsing without syncing:**
```bash
python run.py --dry-run --limit 10
```

**Process all platforms with detailed logging:**
```bash
python run.py --log-level DEBUG --log-file logs/debug.log
```

## Data Structure

### Extracted Booking Data

The system extracts the following data from booking emails:

- **Guest Information**: Name, phone number
- **Booking Details**: Check-in/out dates, reservation ID, property ID
- **Platform Information**: Source platform (Vrbo, Airbnb, Booking.com)
- **Metadata**: Number of guests, email timestamp

### Supabase Structure

```
bookings (table)
| column            | type        |
|-------------------|-------------|
| reservation_id PK | text        |
| platform          | text        |
| guest_name        | text        |
| guest_phone       | text        |
| guest_email       | text        |
| check_in_date     | timestamptz |
| check_out_date    | timestamptz |
| property_id       | text        |
| property_name     | text        |
| number_of_guests  | int4        |
| total_amount      | float8      |
| currency          | text        |
| booking_date      | timestamptz |
| email_id          | text        |
| created_at        | timestamptz |
| updated_at        | timestamptz |
| raw_data          | jsonb       |
```

## Testing

Run the test suite:
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src

# Run specific test file
pytest tests/test_email_reader.py

# Run with verbose output
pytest -v
```

## Development

### Code Quality

The project uses several tools for code quality:

```bash
# Format code
black src/ tests/

# Lint code
flake8 src/ tests/

# Type checking
mypy src/
```

### Adding New Platforms

To add support for a new vacation rental platform:

1. Add platform patterns to `config/settings.py`
2. Implement parsing logic in `src/booking_parser/parser.py`
3. Add tests in `tests/test_booking_parser.py`
4. Update documentation

## Logging

The system provides comprehensive logging:

- **Console Output**: Colorized logs with processing summaries
- **File Logging**: Optional log files for debugging
- **Structured Logging**: JSON-formatted logs for production monitoring

### Log Levels

- `DEBUG`: Detailed debugging information
- `INFO`: General processing information
- `WARNING`: Non-critical issues
- `ERROR`: Errors that need attention

## Error Handling

The system handles various error scenarios:

- **Gmail Connection Issues**: Automatic retry with exponential backoff
- **Email Parsing Failures**: Graceful degradation with detailed error reporting
- **Database Sync Errors**: Duplicate detection and conflict resolution
- **Network Issues**: Connection timeouts and retry logic

## Production Deployment

### Environment Variables

Set these in your production environment:

```bash
# Required
GMAIL_EMAIL=your-email@gmail.com
GMAIL_PASSWORD=your-app-password
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...

# Optional
LOG_LEVEL=INFO
DEFAULT_TIMEZONE=UTC
MAX_EMAILS_PER_RUN=100
```

### Cron Job Example

Set up a cron job to run the system regularly:

```bash
# Run every hour
0 * * * * cd /path/to/vacation_rental_automation && python run.py >> logs/cron.log 2>&1

# Run daily at 9 AM
0 9 * * * cd /path/to/vacation_rental_automation && python run.py --since-days 1 >> logs/daily.log 2>&1
```

## Troubleshooting

### Common Issues

1. **Gmail Connection Failed**
   - Verify IMAP is enabled in Gmail settings
   - Check if using App Password instead of regular password
   - Ensure 2FA is properly configured

2. **Supabase Authentication Error**
   - Verify URL and keys in `.env`
   - Ensure RLS policy allows access for the service role
   - Confirm table names/columns match expectations

3. **Email Parsing Issues**
   - Check if email format has changed
   - Review parsing patterns in `booking_parser/parser.py`
   - Enable DEBUG logging for detailed parsing information

### Getting Help

1. Check the logs for detailed error messages
2. Run with `--dry-run` to test without affecting data
3. Use `--log-level DEBUG` for verbose output
4. Review the test cases for expected behavior

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run the test suite
6. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support and questions:
- Create an issue in the repository
- Check the troubleshooting section
- Review the test cases for usage examples
