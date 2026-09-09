"""Windsor fetcher surfaces the actual error message from Windsor's JSON body
when the upstream returns HTTP 4xx. Without this, operators only see opaque
'HTTP 400: BAD REQUEST' and can't tell whether the failure is auth, validation,
or upstream outage.

This was the bug behind the 'Windsor data is broken, I can't tell why'
recurring complaint.
"""

import importlib
import io
import json
import os
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError


REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
APP_DIR = os.path.join(REPO, 'campaign-os')
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


def _make_http_error(code, msg, body_bytes):
    """Build a real urllib HTTPError with body BytesIO as the fp.
    
    HTTPError.read() reads from self.fp, so fp MUST be set in the constructor
    (post-construction assignment doesn't work).
    """
    return HTTPError(url='https://x', code=code, msg=msg, hdrs={},
                     fp=io.BytesIO(body_bytes))


class WindsorErrorSurfacingTests(unittest.TestCase):

    def _get_client(self):
        if '_lib.windsor_client' in sys.modules:
            del sys.modules['_lib.windsor_client']
        return importlib.import_module('_lib.windsor_client')

    def test_http_400_surfaces_windsor_error_message(self):
        """Windsor returns {"error": "..."} JSON. Surface the text, not the opaque HTTP code."""
        client = self._get_client()
        body = json.dumps({"error": "Please check the API key used: d09f9..."}).encode()
        err = _make_http_error(400, 'BAD REQUEST', body)

        with patch('urllib.request.urlopen', side_effect=err):
            result = client._http_get_json('https://connectors.windsor.ai/facebook?test=1')
        self.assertIn('Please check the API key used', result['error'])
        self.assertEqual(result['status'], 400)
        # Make sure the opaque "HTTP 400: BAD REQUEST" alone is NOT the final message
        self.assertNotEqual(result['error'], 'HTTP 400: BAD REQUEST')

    def test_http_401_with_no_body(self):
        """HTTP 401 with empty body should still return the structured message."""
        client = self._get_client()
        err = _make_http_error(401, 'UNAUTHORIZED', b'')

        with patch('urllib.request.urlopen', side_effect=err):
            result = client._http_get_json('https://x')
        self.assertIn('HTTP 401', result['error'])

    def test_http_500_with_non_json_body(self):
        """Non-JSON body still surfaces the raw text snippet."""
        client = self._get_client()
        body = b'<html>500 Internal Server Error</html>'
        err = _make_http_error(500, 'INTERNAL SERVER ERROR', body)

        with patch('urllib.request.urlopen', side_effect=err):
            result = client._http_get_json('https://x')
        self.assertIn('HTTP 500', result['error'])
        self.assertIn('500 Internal', result['error'])


if __name__ == '__main__':
    unittest.main()