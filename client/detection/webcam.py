"""
Webcam Module - Live Proctoring Feed
=====================================
Initializes and manages webcam feed for live student monitoring.
Captures video frames for real-time proctoring and anomaly detection.

FEATURES:
- OpenCV-based camera initialization
- Frame capture and processing
- Basic video stream management
- Camera device detection and validation

FUTURE ENHANCEMENTS:
- Face detection and recognition
- Gaze tracking for cheating detection
- Person detection (multiple people in view = cheating)
- Emotion recognition
- Video compression and streaming to server
- Local recording with encryption
- AI-based suspicious behavior detection
"""

import cv2
import logging
import threading
import time
from typing import Optional, Tuple, List
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from client.utils.config import (
    WEBCAM_ENABLED,
    WEBCAM_INDEX,
    WEBCAM_RESOLUTION,
    WEBCAM_FPS,
    ENABLE_FACE_DETECTION,
)


class WebcamManager:
    """
    Manages webcam initialization and frame capture.
    Handles video stream for live proctoring.
    """
    
    def __init__(self):
        """Initialize the webcam manager."""
        self.logger = logging.getLogger(__name__)
        self.camera = None
        self.is_streaming = False
        self.current_frame = None
        self.frame_count = 0
        self.face_cascade = None
        
        # Load face detection classifier if enabled
        if ENABLE_FACE_DETECTION:
            self._load_face_detector()
    
    def _load_face_detector(self):
        """
        Load OpenCV cascade classifier for face detection.
        
        STUB: Actual implementation requires:
        - haar/lbp cascade files (included with OpenCV)
        - Proper path resolution
        - Fallback if files not found
        """
        try:
            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            self.face_cascade = cv2.CascadeClassifier(cascade_path)
            
            if self.face_cascade.empty():
                self.logger.warning("Face cascade classifier failed to load")
            else:
                self.logger.info("✓ Face cascade classifier loaded successfully")
        
        except Exception as e:
            self.logger.error(f"Failed to load face detector: {e}")
    
    def initialize_camera(self, camera_index: int = WEBCAM_INDEX) -> bool:
        """
        Initialize camera connection and validate.
        
        Args:
            camera_index (int): Camera device index (0 = default)
            
        Returns:
            bool: True if initialization successful
        """
        if not WEBCAM_ENABLED:
            self.logger.warning("Webcam disabled in configuration")
            return False
        
        try:
            self.logger.info(f"Attempting to initialize camera {camera_index}...")
            
            # Create camera object
            self.camera = cv2.VideoCapture(camera_index)
            
            # Check if camera opened successfully
            if not self.camera.isOpened():
                self.logger.error(f"Failed to open camera {camera_index}")
                return False
            
            # Configure camera properties
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, WEBCAM_RESOLUTION[0])
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, WEBCAM_RESOLUTION[1])
            self.camera.set(cv2.CAP_PROP_FPS, WEBCAM_FPS)
            
            # Verify configuration
            actual_width = int(self.camera.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(self.camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
            actual_fps = self.camera.get(cv2.CAP_PROP_FPS)
            
            self.logger.info(
                f"✓ Camera initialized: {actual_width}x{actual_height} @ {actual_fps} FPS"
            )
            
            return True
        
        except Exception as e:
            self.logger.error(f"Camera initialization error: {e}")
            return False
    
    def capture_frame(self) -> Optional[Tuple[bool, object]]:
        """
        Capture a single frame from the camera.
        
        Returns:
            Tuple[bool, ndarray]: (success, frame) or (False, None)
        """
        if not self.is_streaming or self.camera is None:
            return False, None
        
        try:
            success, frame = self.camera.read()
            
            if success:
                self.current_frame = frame
                self.frame_count += 1
                return True, frame
            else:
                self.logger.warning("Failed to read frame from camera")
                return False, None
        
        except Exception as e:
            self.logger.error(f"Frame capture error: {e}")
            return False, None
    
    def start_streaming(self) -> bool:
        """
        Start continuous camera streaming in background thread.
        
        Returns:
            bool: True if streaming started successfully
        """
        if not self.camera or not self.camera.isOpened():
            if not self.initialize_camera():
                return False
        
        self.is_streaming = True
        self.logger.info("✓ Webcam streaming started")
        
        # Start capture thread
        stream_thread = threading.Thread(target=self._streaming_loop, daemon=True)
        stream_thread.start()
        
        return True
    
    def _streaming_loop(self):
        """
        Background thread for continuous frame capture.
        Runs until streaming is stopped.
        """
        while self.is_streaming:
            try:
                self.capture_frame()
                time.sleep(1.0 / WEBCAM_FPS)
            except Exception as e:
                self.logger.error(f"Streaming loop error: {e}")
                self.is_streaming = False
    
    def stop_streaming(self):
        """Stop webcam streaming and release resources."""
        self.is_streaming = False
        
        if self.camera:
            self.camera.release()
            self.camera = None
        
        self.logger.info("✓ Webcam streaming stopped")
    
    def get_current_frame(self) -> Optional[object]:
        """
        Get the most recently captured frame.
        
        Returns:
            ndarray: Current frame or None if not available
        """
        return self.current_frame
    
    def detect_faces(self, frame: object) -> List[Tuple[int, int, int, int]]:
        """
        Detect faces in a frame using cascade classifier.
        
        FUTURE ENHANCEMENTS:
        - Multi-face detection (flag if >1 person detected)
        - Face recognition to verify student identity
        - Face tracking across frames
        - Emotion analysis
        
        Args:
            frame (ndarray): Input frame to analyze
            
        Returns:
            List[Tuple]: List of face bounding boxes (x, y, w, h)
        """
        if self.face_cascade is None or self.face_cascade.empty():
            return []
        
        try:
            # Convert to grayscale for detection
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Detect faces
            faces = self.face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(30, 30)
            )
            
            return list(faces)
        
        except Exception as e:
            self.logger.error(f"Face detection error: {e}")
            return []
    
    def analyze_frame(self, frame: object = None) -> Dict:
        """
        Perform comprehensive analysis on a frame.
        
        STUB for advanced analysis. Future implementation includes:
        - Face detection and counting
        - Gaze direction estimation
        - Eye closure detection (sleeping/phone use)
        - Multiple person detection (cheating flag)
        - Brightness/blur analysis (video quality check)
        
        Args:
            frame (ndarray): Frame to analyze. If None, uses current_frame
            
        Returns:
            Dict: Analysis results
        """
        if frame is None:
            frame = self.current_frame
        
        if frame is None:
            return {'error': 'No frame available'}
        
        analysis = {
            'frame_number': self.frame_count,
            'timestamp': time.time(),
            'faces_detected': 0,
            'face_count': 0,
            'suspicious_indicators': [],
            'frame_quality': 'UNKNOWN'
        }
        
        # Face detection
        if ENABLE_FACE_DETECTION:
            faces = self.detect_faces(frame)
            analysis['faces_detected'] = len(faces)
            
            # Flag suspicious conditions
            if len(faces) == 0:
                analysis['suspicious_indicators'].append("NO_FACE_DETECTED")
            elif len(faces) > 1:
                analysis['suspicious_indicators'].append("MULTIPLE_PEOPLE")
            
            analysis['face_count'] = len(faces)
        
        # TODO: Add more sophisticated analysis
        # - Gaze tracking
        # - Eye blink detection
        # - Frame blur detection
        # - Lighting analysis
        
        return analysis
    
    def get_statistics(self) -> Dict:
        """
        Get streaming statistics.
        
        Returns:
            Dict: Streaming statistics
        """
        return {
            'is_streaming': self.is_streaming,
            'frames_captured': self.frame_count,
            'camera_available': self.camera is not None and self.camera.isOpened(),
            'face_detection_enabled': ENABLE_FACE_DETECTION,
            'resolution': WEBCAM_RESOLUTION,
            'fps': WEBCAM_FPS
        }


# ============================================================================
# ADVANCED WEBCAM MONITORING STUBS
# ============================================================================

class AdvancedWebcamMonitor(WebcamManager):
    """
    Advanced webcam monitoring with biometric and behavioral analysis.
    
    FUTURE FEATURES:
    - Real-time gaze tracking using deep learning
    - Facial expression analysis (detect stress/cheating behavior)
    - Head pose estimation (looking away from screen = suspicious)
    - Multiple face detection (cheating attempt)
    - Video streaming with H.264 compression to server
    - Deep learning-based anomaly detection
    """
    
    def enable_gaze_tracking(self):
        """
        Initialize gaze tracking system.
        
        FUTURE IMPLEMENTATION:
        - Load pre-trained gaze tracking model
        - Calibrate for each student
        - Real-time gaze point estimation
        """
        pass
    
    def analyze_gaze_trajectory(self, frame: object) -> Dict:
        """
        Analyze student's gaze pattern for suspicious behavior.
        
        FUTURE IMPLEMENTATION:
        - Track where student is looking
        - Detect looking at other screens/people
        - Flag excessive looking away from exam
        
        Returns:
            Dict: Gaze analysis results
        """
        # TODO: Implement gaze tracking
        pass
    
    def detect_multiple_people(self, frame: object) -> bool:
        """
        Detect if multiple people are in frame (cheating indicator).
        
        Args:
            frame (ndarray): Frame to analyze
            
        Returns:
            bool: True if multiple people detected
        """
        # TODO: Implement robust multi-person detection
        pass


if __name__ == "__main__":
    # Test the webcam manager
    manager = WebcamManager()
    
    print("\\n=== Webcam Manager Self-Test ===\\n")
    
    if manager.initialize_camera():
        print("✓ Camera initialized")
        
        if manager.start_streaming():
            print("✓ Streaming started")
            
            # Capture a few frames
            time.sleep(2)
            
            for i in range(5):
                frame = manager.get_current_frame()
                if frame is not None:
                    analysis = manager.analyze_frame(frame)
                    print(f"Frame {i}: {analysis['faces_detected']} faces detected")
                time.sleep(1)
            
            manager.stop_streaming()
            print("✓ Streaming stopped")
    else:
        print("✗ Camera initialization failed")
    
    stats = manager.get_statistics()
    print(f"\\nStatistics: {stats}")
