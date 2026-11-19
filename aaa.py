import os
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading

STATE_FILE = '/data/state.json'

request_counter = {'count': 0}
counter_lock = threading.Lock()

def load_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {'request_count': 0}

def save_state(data):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(data, f, indent=2)

class ConvertHandler(BaseHTTPRequestHandler):
    def do_GET(self):

        with counter_lock:
            request_counter['count'] += 1
            current_count = request_counter['count']

        state = load_state()
        state['request_count'] = current_count
        save_state(state)
    
        parsed_path = urlparse(self.path)
        
        if parsed_path.path == '/health':
            self.send_json(200, {"status": "ok"})
            
        elif parsed_path.path == '/convert':
            query_params = parse_qs(parsed_path.query)
            
            if 'value' not in query_params:
                self.send_json(400, {"error": "Missing 'value' parameter"})
                return
            
            try:
                value = float(query_params['value'][0])
                meters = value * 1000
                self.send_json(200, {
                    "kilometers": value,
                    "meters": meters,
                    "message": os.environ.get('MESSAGE', ''),
                    "version": os.environ.get('APP_VERSION', 'unknown'),
                    "requests_handled": current_count
                })
            except ValueError:
                self.send_json(400, {"error": "Invalid value"})

        elif parsed_path.path == '/stats':
            state = load_state()
            self.send_json(200, state)       
                
        else:
            self.send_json(404, {"error": "Not found"})
    
    def send_json(self, status_code, data):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def log_message(self, format, *args):
        pass

if __name__ == '__main__':
    state = load_state()
    request_counter['count'] = state.get('request_count', 0)
    port = int(os.environ.get('PORT', 8004))
    server = HTTPServer(('0.0.0.0', port), ConvertHandler)
    print(f"Server running on port {port}")
    print(f"Previous request count: {request_counter['count']}")
    server.serve_forever()