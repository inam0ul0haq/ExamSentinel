"""
ExamSentinel Client - Main Entry Point
=======================================
Initializes and runs the secure exam desktop browser application.

Main responsibilities:
1. Load configuration
2. Setup logging
3. Initialize all security modules
4. Launch Tkinter UI
5. Handle graceful shutdown

EXECUTION:
    python main.py

REQUIREMENTS:
    - Python 3.8+
    - All packages in requirements.txt installed
    - Windows OS (uses Windows-specific APIs)
"""

import sys
import logging
from pathlib import Path
import tkinter as tk

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import configuration and UI
from client.utils.config import (
    APP_NAME,
    APP_VERSION,
    LOG_DIRECTORY,
    LOG_LEVEL,
    VERBOSE_LOGGING,
)
from client.ui.exam_ui import ExamUI


# ============================================================================
# LOGGING SETUP
# ============================================================================

def setup_logging():
    """
    Configure logging for the application.
    Creates both file and console handlers.
    """
    # Create logs directory
    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    
    # Create logger
    logger = logging.getLogger()
    logger.setLevel(LOG_LEVEL)
    
    # File handler
    log_file = LOG_DIRECTORY / f"{APP_NAME}_{Path.cwd().name}.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(LOG_LEVEL)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(LOG_LEVEL if VERBOSE_LOGGING else logging.INFO)
    
    # Formatter
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


# ============================================================================
# STARTUP SEQUENCE
# ============================================================================

def startup_banner():
    """Display startup banner with version info."""
    banner = f"""
╔════════════════════════════════════════════════════════════════╗
║                                                                ║
║          🔐 {APP_NAME.upper()}                                  ║
║          Secure Exam Desktop Browser v{APP_VERSION}                        ║
║                                                                ║
║   [Research Project] Stealth VM Detection & Proctoring        ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝
"""
    print(banner)


def startup_checks():
    """
    Perform pre-flight checks before launching exam.
    Validates environment and required dependencies.
    """
    logger = logging.getLogger(__name__)
    
    logger.info("="*60)
    logger.info(f"Starting {APP_NAME} v{APP_VERSION}")
    logger.info("="*60)
    
    # Check platform
    if sys.platform != "win32":
        logger.error("❌ This application requires Windows OS")
        return False
    
    logger.info("✓ Running on Windows")
    
    # Check Python version
    if sys.version_info < (3, 8):
        logger.error(f"❌ Python 3.8+ required, got {sys.version_info.major}.{sys.version_info.minor}")
        return False
    
    logger.info(f"✓ Python {sys.version_info.major}.{sys.version_info.minor}")
    
    # Check required packages
    required_packages = ['psutil', 'cv2', 'flask']
    missing = []
    
    for package in required_packages:
        try:
            __import__(package)
            logger.info(f"✓ {package} available")
        except ImportError:
            logger.warning(f"⚠ {package} not found")
            missing.append(package)
    
    if missing:
        logger.error(f"❌ Missing packages: {', '.join(missing)}")
        logger.error("   Install with: pip install -r requirements.txt")
        return False
    
    logger.info("="*60)
    logger.info("✓ All startup checks passed")
    logger.info("="*60)
    
    return True


# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    """
    Main entry point for ExamSentinel client.
    Initializes logging, runs startup checks, and launches UI.
    """
    
    # Display banner
    startup_banner()
    
    # Setup logging
    logger = setup_logging()
    
    # Run startup checks
    if not startup_checks():
        logger.critical("Startup checks failed. Exiting.")
        return 1
    
    try:
        # Create and run Tkinter application
        logger.info("Initializing Exam UI...")
        
        root = tk.Tk()
        app = ExamUI(root)
        
        logger.info("✓ UI initialized successfully")
        logger.info("Launching ExamSentinel...")
        
        # Run main event loop
        root.mainloop()
        
        logger.info("ExamSentinel closed normally")
        return 0
    
    except Exception as e:
        logger.critical(f"Critical error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
