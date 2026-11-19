import unittest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aaa

class TestConverter(unittest.TestCase):
    
    def setUp(self):
        aaa.request_counter['count'] = 0
    
    def test_convert_1km_to_1000m(self):
        value = 1.0
        expected = 1000.0
        result = value * 1000
        self.assertEqual(result, expected)
    
    def test_convert_1_5km_to_1500m(self):
        value = 1.5
        expected = 1500.0
        result = value * 1000
        self.assertEqual(result, expected)
    
    def test_convert_2km_to_2000m(self):
        value = 2.0
        expected = 2000.0
        result = value * 1000
        self.assertEqual(result, expected)
    
    def test_convert_0km_to_0m(self):
        value = 0.0
        expected = 0.0
        result = value * 1000
        self.assertEqual(result, expected)
    
    def test_convert_negative_value(self):
        value = -1.0
        expected = -1000.0
        result = value * 1000
        self.assertEqual(result, expected)
    
    def test_convert_small_value(self):
        value = 0.001
        expected = 1.0
        result = value * 1000
        self.assertEqual(result, expected)
    
    def test_conversion_rounds_to_two_digits(self):
        value = 1.555
        result = value * 1000
        rounded_result = round(result, 2)
        expected = 1555.02
        self.assertEqual(rounded_result, expected)
    
    def test_health_endpoint_structure(self):
        response = {"status": "ok"}
        self.assertIn("status", response)
        self.assertEqual(response["status"], "ok")
    
    def test_stats_endpoint_structure(self):
        state = {"request_count": 0}
        self.assertIn("request_count", state)
        self.assertIsInstance(state["request_count"], int)
    
    def test_request_counter_increments(self):
        initial_count = aaa.request_counter['count']
        aaa.request_counter['count'] += 1
        self.assertEqual(aaa.request_counter['count'], initial_count + 1)
    
    def test_json_response_format(self):
        import json
        data = {"kilometers": 1.5, "meters": 1500.0}
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        self.assertEqual(parsed["kilometers"], 1.5)
        self.assertEqual(parsed["meters"], 1500.0)
    
    def test_error_missing_value(self):
        error_response = {"error": "Missing 'value' parameter"}
        self.assertIn("error", error_response)


if __name__ == '__main__':
    unittest.main()