"""
Logging utility for the Vacation Rental Booking Automation system.
"""
import logging
import sys
from typing import Optional
from colorama import Fore, Style, init
import structlog
from datetime import datetime

# Initialize colorama for cross-platform colored output
init(autoreset=True)


class ColorizedFormatter(logging.Formatter):
    """Custom formatter with colorized output."""
    
    COLORS = {
        'DEBUG': Fore.CYAN,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.MAGENTA + Style.BRIGHT,
    }
    
    def format(self, record):
        # Add color to the level name
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{Style.RESET_ALL}"
        
        # Add color to the message for errors and warnings
        if record.levelno >= logging.WARNING:
            record.msg = f"{Fore.RED}{record.msg}{Style.RESET_ALL}"
        elif record.levelno == logging.INFO:
            record.msg = f"{Fore.GREEN}{record.msg}{Style.RESET_ALL}"
        
        return super().format(record)


def setup_logger(
    name: str = "vacation_rental_automation",
    level: str = "INFO",
    log_file: Optional[str] = None
) -> structlog.BoundLogger:
    """
    Set up structured logging with colorized console output.
    
    Args:
        name: Logger name
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path for logging to file
        
    Returns:
        Configured structured logger
    """
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer() if log_file else structlog.dev.ConsoleRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Get the logger
    logger = structlog.get_logger(name)
    
    # Set up standard library logging
    stdlib_logger = logging.getLogger(name)
    stdlib_logger.setLevel(getattr(logging, level.upper()))
    
    # Console handler with colorized output
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = ColorizedFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    stdlib_logger.addHandler(console_handler)
    
    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        stdlib_logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str = "vacation_rental_automation") -> structlog.BoundLogger:
    """
    Get a configured logger instance.
    
    Args:
        name: Logger name
        
    Returns:
        Configured structured logger
    """
    return structlog.get_logger(name)


class BookingLogger:
    """Specialized logger for booking operations with summary tracking."""
    
    def __init__(self, logger: structlog.BoundLogger):
        self.logger = logger
        self.stats = {
            'emails_processed': 0,
            'bookings_parsed': 0,
            'new_bookings': 0,
            'duplicate_bookings': 0,
            'errors': 0,
            'platforms': {}
        }
    
    def log_email_processed(self, platform: str, email_id: str):
        """Log when an email is processed."""
        self.stats['emails_processed'] += 1
        if platform not in self.stats['platforms']:
            self.stats['platforms'][platform] = 0
        self.stats['platforms'][platform] += 1
        self.logger.info("Email processed", platform=platform, email_id=email_id)
    
    def log_booking_parsed(self, booking_data: dict):
        """Log when a booking is successfully parsed."""
        self.stats['bookings_parsed'] += 1
        self.logger.info(
            "Booking parsed successfully",
            reservation_id=booking_data.get('reservation_id'),
            platform=booking_data.get('platform'),
            guest_name=booking_data.get('guest_name')
        )
    
    def log_new_booking(self, booking_data: dict):
        """Log when a new booking is added to Firestore."""
        self.stats['new_bookings'] += 1
        self.logger.info(
            "New booking added to Firestore",
            reservation_id=booking_data.get('reservation_id'),
            platform=booking_data.get('platform')
        )
    
    def log_duplicate_booking(self, reservation_id: str, platform: str):
        """Log when a duplicate booking is found."""
        self.stats['duplicate_bookings'] += 1
        self.logger.warning(
            "Duplicate booking found",
            reservation_id=reservation_id,
            platform=platform
        )
    
    def log_error(self, error: Exception, context: str = ""):
        """Log an error."""
        self.stats['errors'] += 1
        self.logger.error(
            "Error occurred",
            error=str(error),
            error_type=type(error).__name__,
            context=context
        )
    
    def print_summary(self):
        """Print a summary of all operations."""
        self.logger.info(
            "Processing summary",
            emails_processed=self.stats['emails_processed'],
            bookings_parsed=self.stats['bookings_parsed'],
            new_bookings=self.stats['new_bookings'],
            duplicate_bookings=self.stats['duplicate_bookings'],
            errors=self.stats['errors'],
            platforms=self.stats['platforms']
        )
        
        # Print colored summary to console
        print(f"\n{Fore.CYAN}{'='*50}")
        print(f"{Fore.WHITE}PROCESSING SUMMARY")
        print(f"{Fore.CYAN}{'='*50}")
        print(f"{Fore.GREEN}✓ Emails processed: {self.stats['emails_processed']}")
        print(f"{Fore.GREEN}✓ Bookings parsed: {self.stats['bookings_parsed']}")
        print(f"{Fore.BLUE}✓ New bookings: {self.stats['new_bookings']}")
        print(f"{Fore.YELLOW}⚠ Duplicate bookings: {self.stats['duplicate_bookings']}")
        print(f"{Fore.RED}✗ Errors: {self.stats['errors']}")
        
        if self.stats['platforms']:
            print(f"\n{Fore.WHITE}By Platform:")
            for platform, count in self.stats['platforms'].items():
                print(f"  {Fore.CYAN}{platform}: {count}")
        
        print(f"{Fore.CYAN}{'='*50}\n")
    
    def reset_stats(self):
        """Reset statistics."""
        self.stats = {
            'emails_processed': 0,
            'bookings_parsed': 0,
            'new_bookings': 0,
            'duplicate_bookings': 0,
            'errors': 0,
            'platforms': {}
        }
