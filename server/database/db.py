"""
Database Module - MySQL Connection Management
==============================================
Handles database connections, query execution, and schema management.
Provides abstraction layer for secure database operations.

FEATURES:
- Connection pooling
- Parameterized queries (SQL injection prevention)
- Transaction management
- Error handling and logging

FUTURE ENHANCEMENTS:
- ORM integration (SQLAlchemy)
- Database migration system
- Query caching
- Backup automation
- Encryption at rest
"""

import mysql.connector
from mysql.connector import Error, pooling
import logging
from typing import Optional, List, Dict, Any
import os

# Configuration
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "exam_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "secure_password")
DB_NAME = os.getenv("DB_NAME", "exam_sentinel_db")
DB_PORT = int(os.getenv("DB_PORT", 3306))


class DatabaseManager:
    """
    Manages MySQL database connections and operations.
    Provides safe, parameterized database access.
    """
    
    def __init__(self):
        """Initialize database manager with connection pool."""
        self.logger = logging.getLogger(__name__)
        self.connection_pool = None
        self._initialize_pool()
    
    def _initialize_pool(self):
        """
        Create connection pool for efficient database access.
        Reduces overhead of creating new connections per request.
        """
        try:
            self.connection_pool = pooling.MySQLConnectionPool(
                pool_name="exam_sentinel_pool",
                pool_size=5,
                pool_reset_session=True,
                host=DB_HOST,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                port=DB_PORT,
                autocommit=True  # Each query commits automatically
            )
            self.logger.info("✓ Database connection pool initialized")
        except Error as e:
            self.logger.error(f"Failed to initialize connection pool: {e}")
            self.connection_pool = None
    
    def get_connection(self):
        """
        Get a connection from the pool.
        
        Returns:
            mysql.connector.MySQLConnection or None
        """
        if self.connection_pool is None:
            self.logger.error("Connection pool not initialized")
            return None
        
        try:
            return self.connection_pool.get_connection()
        except Error as e:
            self.logger.error(f"Failed to get database connection: {e}")
            return None
    
    def execute_query(self, query: str, params: Dict = None) -> Optional[List[Dict]]:
        """
        Execute a SELECT query and return results.
        Uses parameterized queries to prevent SQL injection.
        
        Args:
            query (str): SQL query with {} placeholders
            params (Dict): Parameters to substitute
            
        Returns:
            List[Dict]: Query results or None on error
        """
        if params is None:
            params = {}
        
        connection = self.get_connection()
        if connection is None:
            return None
        
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(query, params)
            results = cursor.fetchall()
            cursor.close()
            return results
        except Error as e:
            self.logger.error(f"Query execution error: {e}")
            return None
        finally:
            connection.close()
    
    def execute_update(self, query: str, params: Dict = None) -> bool:
        """
        Execute INSERT, UPDATE, or DELETE query.
        
        Args:
            query (str): SQL query with {} placeholders
            params (Dict): Parameters to substitute
            
        Returns:
            bool: True if successful, False otherwise
        """
        if params is None:
            params = {}
        
        connection = self.get_connection()
        if connection is None:
            return False
        
        try:
            cursor = connection.cursor()
            cursor.execute(query, params)
            connection.commit()
            affected = cursor.rowcount
            cursor.close()
            
            self.logger.debug(f"Query executed: {affected} rows affected")
            return True
        except Error as e:
            self.logger.error(f"Update execution error: {e}")
            connection.rollback()
            return False
        finally:
            connection.close()
    
    def test_connection(self) -> bool:
        """
        Test database connectivity.
        
        Returns:
            bool: True if connection successful
        """
        try:
            connection = self.get_connection()
            if connection is None:
                return False
            
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            connection.close()
            
            self.logger.info("✓ Database connection test successful")
            return True
        except Error as e:
            self.logger.error(f"Database connection test failed: {e}")
            return False


# ============================================================================
# SCHEMA INITIALIZATION
# ============================================================================

def initialize_database():
    """
    Create database tables if they don't exist.
    Call this once on first server startup.
    """
    db = DatabaseManager()
    
    # Student accounts table
    create_students_table = """
    CREATE TABLE IF NOT EXISTS students (
        student_id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(50) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        email VARCHAR(100) UNIQUE NOT NULL,
        full_name VARCHAR(100),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_username (username)
    )
    """
    
    # Exam sessions table
    create_sessions_table = """
    CREATE TABLE IF NOT EXISTS exam_sessions (
        session_id INT AUTO_INCREMENT PRIMARY KEY,
        student_id INT NOT NULL,
        exam_name VARCHAR(100),
        start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        end_time TIMESTAMP NULL,
        machine_id VARCHAR(100),
        ip_address VARCHAR(45),
        session_token VARCHAR(255) UNIQUE,
        status ENUM('ACTIVE', 'COMPLETED', 'TERMINATED') DEFAULT 'ACTIVE',
        FOREIGN KEY (student_id) REFERENCES students(student_id),
        INDEX idx_student (student_id),
        INDEX idx_timestamp (start_time)
    )
    """
    
    # Security logs table
    create_logs_table = """
    CREATE TABLE IF NOT EXISTS security_logs (
        log_id INT AUTO_INCREMENT PRIMARY KEY,
        session_id INT NOT NULL,
        log_type VARCHAR(50),
        severity ENUM('INFO', 'WARNING', 'CRITICAL') DEFAULT 'INFO',
        message VARCHAR(500),
        data JSON,
        vm_score FLOAT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES exam_sessions(session_id),
        INDEX idx_session (session_id),
        INDEX idx_severity (severity),
        INDEX idx_timestamp (timestamp)
    )
    """
    
    # VM detection results table
    create_vm_results_table = """
    CREATE TABLE IF NOT EXISTS vm_detection_results (
        result_id INT AUTO_INCREMENT PRIMARY KEY,
        session_id INT NOT NULL,
        detection_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        final_score FLOAT NOT NULL,
        cpu_score FLOAT,
        thermal_score FLOAT,
        hardware_score FLOAT,
        recommendation VARCHAR(200),
        raw_data JSON,
        FOREIGN KEY (session_id) REFERENCES exam_sessions(session_id),
        INDEX idx_session (session_id),
        INDEX idx_score (final_score)
    )
    """
    
    # Create tables
    tables = {
        'students': create_students_table,
        'exam_sessions': create_sessions_table,
        'security_logs': create_logs_table,
        'vm_detection_results': create_vm_results_table,
    }
    
    logger = logging.getLogger(__name__)
    
    for table_name, create_sql in tables.items():
        try:
            db.execute_update(create_sql)
            logger.info(f"✓ Table '{table_name}' initialized")
        except Exception as e:
            logger.error(f"Failed to create table '{table_name}': {e}")


# ============================================================================
# DATABASE QUERIES (Stubs for future ORM migration)
# ============================================================================

class StudentQueries:
    """Database queries for student management."""
    
    @staticmethod
    def create_student(username: str, password_hash: str, email: str, full_name: str) -> bool:
        """
        Create a new student account.
        
        Args:
            username (str): Unique username
            password_hash (str): Hashed password
            email (str): Student email
            full_name (str): Full name
            
        Returns:
            bool: True if successful
        """
        db = DatabaseManager()
        query = """
        INSERT INTO students (username, password_hash, email, full_name)
        VALUES (%(username)s, %(password)s, %(email)s, %(name)s)
        """
        return db.execute_update(query, {
            'username': username,
            'password': password_hash,
            'email': email,
            'name': full_name
        })
    
    @staticmethod
    def get_student_by_username(username: str) -> Optional[Dict]:
        """
        Retrieve student by username.
        
        Args:
            username (str): Student username
            
        Returns:
            Dict: Student info or None
        """
        db = DatabaseManager()
        query = "SELECT * FROM students WHERE username = %(username)s"
        results = db.execute_query(query, {'username': username})
        return results[0] if results else None
    
    @staticmethod
    def authenticate_student(username: str, password_hash: str) -> Optional[Dict]:
        """
        Authenticate student credentials.
        
        Args:
            username (str): Student username
            password_hash (str): Hashed password
            
        Returns:
            Dict: Student info if authenticated, None otherwise
        """
        student = StudentQueries.get_student_by_username(username)
        
        if student and student['password_hash'] == password_hash:
            return student
        return None


class SessionQueries:
    """Database queries for exam session management."""
    
    @staticmethod
    def create_session(student_id: int, exam_name: str, machine_id: str, ip_address: str) -> Optional[str]:
        """
        Create an exam session.
        
        Args:
            student_id (int): Student ID
            exam_name (str): Exam name/code
            machine_id (str): Client machine identifier
            ip_address (str): Client IP address
            
        Returns:
            str: Session token or None
        """
        # TODO: Generate secure session token
        token = f"token_{student_id}_{__import__('time').time()}"
        
        db = DatabaseManager()
        query = """
        INSERT INTO exam_sessions (student_id, exam_name, machine_id, ip_address, session_token)
        VALUES (%(student_id)s, %(exam)s, %(machine_id)s, %(ip)s, %(token)s)
        """
        
        success = db.execute_update(query, {
            'student_id': student_id,
            'exam': exam_name,
            'machine_id': machine_id,
            'ip': ip_address,
            'token': token
        })
        
        return token if success else None


class LogQueries:
    """Database queries for security logging."""
    
    @staticmethod
    def record_log(session_id: int, log_type: str, severity: str, message: str, data: Dict = None) -> bool:
        """
        Record a security log entry.
        
        Args:
            session_id (int): Exam session ID
            log_type (str): Type of log (e.g., 'PROCESS_TERMINATION', 'VM_DETECTION')
            severity (str): Log level (INFO, WARNING, CRITICAL)
            message (str): Log message
            data (Dict): Additional JSON data
            
        Returns:
            bool: True if successful
        """
        db = DatabaseManager()
        import json
        
        query = """
        INSERT INTO security_logs (session_id, log_type, severity, message, data)
        VALUES (%(session_id)s, %(type)s, %(severity)s, %(message)s, %(data)s)
        """
        
        return db.execute_update(query, {
            'session_id': session_id,
            'type': log_type,
            'severity': severity,
            'message': message,
            'data': json.dumps(data) if data else None
        })


if __name__ == "__main__":
    # Test database connection
    db = DatabaseManager()
    
    print("\\n=== Database Manager Self-Test ===\\n")
    
    if db.test_connection():
        print("✓ Database connection successful")
        
        # Initialize tables
        print("\\nInitializing database schema...")
        initialize_database()
    else:
        print("✗ Database connection failed")
