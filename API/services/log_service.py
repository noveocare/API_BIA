import threading
import queue
import time
import hashlib
import atexit
from datetime import datetime
from typing import Optional, Dict, Any, List


class AsyncLogBuffer:
    """
    Buffer asynchrone singleton pour les logs.
    Regroupe les insertions par batch pour minimiser la charge SQL Server.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._queue: queue.Queue = queue.Queue(maxsize=10000)
        self._batch_size = 50  # Logs par batch
        self._flush_interval = 3  # Secondes entre flush
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._initialized = True
        self._start_worker()
        
        # Flush à l'arrêt de l'application
        atexit.register(self.shutdown)
    
    def _start_worker(self):
        """Démarre le worker thread."""
        if self._worker_thread is None or not self._worker_thread.is_alive():
            self._stop_event.clear()
            self._worker_thread = threading.Thread(
                target=self._worker_loop, 
                daemon=True,
                name="LogBufferWorker"
            )
            self._worker_thread.start()
    
    def _worker_loop(self):
        """Boucle du worker : flush périodique."""
        while not self._stop_event.is_set():
            time.sleep(self._flush_interval)
            self._flush_batch()
        # Flush final
        self._flush_batch(force=True)
    
    def _flush_batch(self, force: bool = False):
        """Écrit un batch de logs en base."""
        logs: List[Dict] = []
        
        # Vider la queue jusqu'au batch_size
        while len(logs) < self._batch_size:
            try:
                logs.append(self._queue.get_nowait())
            except queue.Empty:
                break
        
        # Si force=True, continuer à vider
        if force:
            while True:
                try:
                    logs.append(self._queue.get_nowait())
                except queue.Empty:
                    break
        
        if not logs:
            return
        
        self._bulk_insert(logs)
    
    def _bulk_insert(self, logs: List[Dict]):
        try:
            from API.models import APILog
            
            log_objects = [
                APILog(
                    timestamp=log['timestamp'],
                    level=log['level'],
                    user_id=log['user_id'],
                    username=log['username'],
                    endpoint=log['endpoint'],
                    method=log['method'],
                    status_code=log['status_code'],
                    execution_time_ms=log['execution_time_ms'],
                    client_ip_hash=log['client_ip_hash'],
                    error_message=log['error_message'],
                    request_body=log['request_body'],  # <-- NOUVEAU
                )
                for log in logs
            ]
            
            APILog.objects.bulk_create(log_objects)
            
        except Exception as e:
            print(f"[LOG ERROR] Impossible d'insérer {len(logs)} logs: {e}")
            
    def log(self, log_entry: Dict[str, Any]):
        """Ajoute un log au buffer (non-bloquant)."""
        try:
            self._queue.put_nowait(log_entry)
        except queue.Full:
            # Buffer plein = on drop le log (mieux que bloquer l'API)
            pass
    
    def shutdown(self):
        """Arrêt propre avec flush final."""
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5)


# Singleton global
_log_buffer: Optional[AsyncLogBuffer] = None


def get_log_buffer() -> AsyncLogBuffer:
    """Récupère l'instance du buffer (lazy init)."""
    global _log_buffer
    if _log_buffer is None:
        _log_buffer = AsyncLogBuffer()
    return _log_buffer


def hash_ip(ip: Optional[str]) -> Optional[str]:
    """Hash l'IP (RGPD) - garde juste 16 chars."""
    if not ip:
        return None
    return ip


def log_api_call(
    endpoint: str,
    method: str,
    status_code: int,
    execution_time_ms: int,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    client_ip: Optional[str] = None,
    error_message: Optional[str] = None,
    request_body: Optional[str] = None,  # <-- NOUVEAU
    level: str = 'INFO'
):
    """Fonction utilitaire pour logger un appel API."""
    log_entry = {
        'timestamp': datetime.now(),
        'level': level[:5],
        'user_id': user_id,
        'username': username[:150] if username else None,
        'endpoint': endpoint[:255],
        'method': method[:10],
        'status_code': status_code,
        'execution_time_ms': execution_time_ms,
        'client_ip_hash': hash_ip(client_ip),
        'error_message': error_message[:1000] if error_message else None,
        'request_body': request_body,  # <-- NOUVEAU
    }
    get_log_buffer().log(log_entry)