"""
A stand-in for the calling system, for testing without placing calls.

    python fake_caller_api.py

Listens on port 8000 and prints every request body it receives, so the
whole path -- worker, payload, HTTP, notification record -- can be
verified before pointing at the real service.

Point the worker at it with the default CALLER_API_BASE_URL
(http://localhost:8000), set CALLS_ENABLED=true, and run:

    python reminder_worker.py --once
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 8000


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(length) if length else b''

        print(f'\n=== POST {self.path} ===')
        pass_key = self.headers.get('x-pass-key')
        print(f'x-pass-key: {pass_key or "(missing)"}')
        auth = self.headers.get('Authorization')
        if auth:
            print(f'Authorization: {auth}')
        try:
            body = json.loads(raw or b'{}')
            print(json.dumps(body, indent=2))
            variables = body.get('assistant_overrides', {}).get(
                'variable_values', {})
            if variables.get('phone_number'):
                print(f'\n--> would dial {variables["phone_number"]} as '
                      f'{variables.get("agent_name")} for '
                      f'{variables.get("candidate_name")}')
        except ValueError:
            print(raw.decode('utf-8', errors='replace'))

        response = json.dumps({'call_id': 'fake-call-0001',
                               'status': 'queued'}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    print(f'Fake calling system listening on http://localhost:{PORT}')
    print('Every call request will be printed here. Ctrl-C to stop.\n')
    HTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
