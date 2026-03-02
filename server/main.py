"""
ExamSentinel Server - Flask REST API Backend
==============================================
Main server application for exam monitoring, authentication, and security logging.

FEATURES:
- RESTful API for client communication
- Student authentication and session management
- Security log collection and storage
- VM detection result processing
- Database integration (MySQL)
- CORS support for development
- Comprehensive error handling

ARCHITECTURE:
- Flask application factory pattern
- Blueprints for modular route organization
- Centralized error handling
- Request/response logging
- Health check endpoints

EXECUTION:
    python main.py

ENVIRONMENT VARIABLES:
    - FLASK_ENV: 'development' or 'production'
    - FLASK_DEBUG: Enable debug mode
    - DB_HOST: Database hostname
    - DB_USER: Database username
    - DB_PASSWORD: Database password
    - DB_NAME: Database name
    - SERVER_HOST: Server hostname (default: 0.0.0.0)
    - SERVER_PORT: Server port (default: 5000)
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import logging
from pathlib import Path
import os
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import routes
from server.routes.auth import auth_bp
from server.routes.logs import logs_bp
from server.database.db import DatabaseManager, initialize_database


# ============================================================================
# FLASK APPLICATION FACTORY
# ============================================================================

def create_app(config_name='development'):
    """
    Create and configure Flask application.
    
    Args:
        config_name (str): Configuration environment
        
    Returns:
        Flask: Configured Flask application
    """
    
    app = Flask(__name__)
    
    # Configuration
    app.config['JSON_SORT_KEYS'] = False
    app.config['PROPAGATE_EXCEPTIONS'] = True
    
    if config_name == 'production':
        app.config['DEBUG'] = False
        app.config['SESSION_COOKIE_SECURE'] = True
        app.config['SESSION_COOKIE_HTTPONLY'] = True
    else:
        app.config['DEBUG'] = True
        app.config['CORS'] = True
    
    # Enable CORS (development)
    CORS(app)
    
    # Setup logging
    _setup_logging(app)
    
    # Initialize database
    app.logger.info("Initializing database...")
    try:
        initialize_database()
        app.logger.info("✓ Database initialized")
    except Exception as e:
        app.logger.error(f"Database initialization failed: {e}")
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(logs_bp)
    
    # Register error handlers
    _register_error_handlers(app)
    
    # Register request/response hooks
    _register_hooks(app)
    
    # Register health check routes
    _register_health_routes(app)
    
    return app


# ============================================================================
# LOGGING SETUP
# ============================================================================

def _setup_logging(app):
    """
    Configure application logging.
    
    Args:
        app (Flask): Flask application instance
    """
    
    # Create logs directory
    log_dir = Path.cwd() / 'logs'
    log_dir.mkdir(exist_ok=True)
    
    # File handler
    log_file = log_dir / 'exam_sentinel_server.log'
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # Formatter
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Add handlers
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(logging.DEBUG)
    
    app.logger.info("Logging initialized")


# ============================================================================
# ERROR HANDLERS
# ============================================================================

def _register_error_handlers(app):
    """
    Register global error handlers.
    
    Args:
        app (Flask): Flask application instance
    """
    
    @app.errorhandler(400)
    def bad_request(error):
        """Handle 400 Bad Request."""
        return jsonify({
            'success': False,
            'error': 'Bad request',
            'message': str(error)
        }), 400
    
    @app.errorhandler(401)
    def unauthorized(error):
        """Handle 401 Unauthorized."""
        return jsonify({
            'success': False,
            'error': 'Unauthorized',
            'message': 'Authentication required'
        }), 401
    
    @app.errorhandler(403)
    def forbidden(error):
        """Handle 403 Forbidden."""
        return jsonify({
            'success': False,
            'error': 'Forbidden',
            'message': 'Access denied'
        }), 403
    
    @app.errorhandler(404)
    def not_found(error):
        """Handle 404 Not Found."""
        return jsonify({
            'success': False,
            'error': 'Not found',
            'message': 'Resource not found'
        }), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 Internal Server Error."""
        app.logger.error(f"Internal error: {error}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'message': 'An unexpected error occurred'
        }), 500


# ============================================================================
# REQUEST/RESPONSE HOOKS
# ============================================================================

def _register_hooks(app):
    """
    Register request/response lifecycle hooks.
    
    Args:
        app (Flask): Flask application instance
    """
    
    @app.before_request
    def log_request():
        """Log incoming requests."""
        app.logger.debug(
            f"{request.method} {request.path} from {request.remote_addr}"
        )
    
    @app.after_request
    def log_response(response):
        """Log outgoing responses."""
        app.logger.debug(
            f"Response: {response.status_code} for {request.method} {request.path}"
        )
        return response


# ============================================================================
# HEALTH CHECK ROUTES
# ============================================================================

def _register_health_routes(app):
    """
    Register health check and status routes.
    
    Args:
        app (Flask): Flask application instance
    """
    
    @app.route('/health', methods=['GET'])
    def health_check():
        """
        Health check endpoint.
        
        Returns:
            JSON response with server status
        """
        db = DatabaseManager()
        db_healthy = db.test_connection()
        
        return jsonify({
            'status': 'healthy' if db_healthy else 'degraded',
            'api_version': '1.0.0',
            'database': 'connected' if db_healthy else 'disconnected'
        }), 200 if db_healthy else 503
    
    @app.route('/api/status', methods=['GET'])
    def api_status():
        """
        Detailed server status endpoint.
        
        Returns:
            JSON response with detailed status
        """
        
        db = DatabaseManager()
        db_status = db.test_connection()
        
        return jsonify({
            'success': True,
            'server_status': 'operational',
            'api_version': '1.0.0',
            'components': {
                'database': 'connected' if db_status else 'disconnected',
                'auth': 'operational',
                'logging': 'operational'
            },
            'timestamp': __import__('time').time()
        }), 200
    
    @app.route('/', methods=['GET'])
    def index():
        """
        Welcome endpoint.
        
        Returns:
            JSON response with API information
        """
        return jsonify({
            'name': 'ExamSentinel Server',
            'version': '0.1.0',
            'description': 'Secure exam monitoring and VM detection',
            'endpoints': {
                'auth': {
                    'POST /api/auth/login': 'Student authentication',
                    'GET /api/auth/validate': 'Token validation',
                    'POST /api/auth/logout': 'Session termination'
                },
                'logs': {
                    'POST /api/logs/submit': 'Submit security logs',
                    'POST /api/logs/vm-detection': 'Submit VM detection results',
                    'GET /api/logs/session/<id>': 'Retrieve session logs'
                },
                'health': {
                    'GET /health': 'Health check',
                    'GET /api/status': 'Detailed status'
                }
            }
        }), 200


# ============================================================================
# STARTUP AND SHUTDOWN
# ============================================================================

def run_server(host='0.0.0.0', port=5000, debug=False):
    """
    Run the Flask development server.
    
    Args:
        host (str): Server host
        port (int): Server port
        debug (bool): Enable debug mode
    """
    
    app = create_app('development' if debug else 'production')
    
    print(f"""
╔════════════════════════════════════════════════════════════════╗
║                                                                ║
║          🛡️  ExamSentinel Server v0.1.0                        ║
║          Secure Exam Monitoring & Proctoring API              ║
║                                                                ║
║  Starting server: {host}:{port}                             ║
║  Debug mode: {'ON' if debug else 'OFF'}                                  ║
║                                                                ║
║  Routes:                                                       ║
║  - Authentication: POST /api/auth/login                        ║
║  - Logs: POST /api/logs/submit                                 ║
║  - Health: GET /health                                         ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝
    """)
    
    # Run server
    app.run(host=host, port=port, debug=debug, use_reloader=False)


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='ExamSentinel Server')
    parser.add_argument('--host', default='0.0.0.0', help='Server host (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=5000, help='Server port (default: 5000)')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    run_server(host=args.host, port=args.port, debug=args.debug)
